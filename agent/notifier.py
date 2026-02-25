import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

import agent.event_bus as bus
from agent.config import settings
from agent.venice_client import VeniceClient
from agent.voice_generator import (
    generate_recovery_complete_voice,
    generate_recovery_started_voice,
    generate_service_down_voice,
)
from agent.card_generator import generate_incident_card

logger = logging.getLogger("akashguard.notifier")


class TelegramNotifier:

    def __init__(self) -> None:
        self._base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self._chat_id = settings.telegram_chat_id
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._enabled = bool(settings.telegram_bot_token and settings.telegram_chat_id)
        self.venice = VeniceClient()
        if not self._enabled:
            logger.warning("Telegram notifier disabled: missing bot token or chat ID")

    # ------------------------------------------------------------------
    # Low-level Telegram methods
    # ------------------------------------------------------------------

    async def send_message(self, text: str, parse_mode: str | None = None) -> bool:
        """Send a plain text message via Telegram sendMessage."""
        if not self._enabled:
            logger.debug("Telegram disabled, skipping message")
            return False
        try:
            payload: dict = {"chat_id": self._chat_id, "text": text}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            resp = await self._client.post(
                f"{self._base_url}/sendMessage",
                json=payload,
            )
            if resp.status_code == 200:
                logger.debug("Telegram message sent")
                return True
            logger.warning("Telegram sendMessage failed: status=%s body=%s", resp.status_code, resp.text[:200])
            return False
        except Exception as exc:
            logger.warning("Telegram sendMessage error: %s", exc)
            return False

    async def send_voice(self, audio_bytes: bytes, caption: str) -> bool:
        """Send a voice note via Telegram sendVoice."""
        if not self._enabled:
            logger.debug("Telegram disabled, skipping voice")
            return False
        try:
            resp = await self._client.post(
                f"{self._base_url}/sendVoice",
                data={"chat_id": self._chat_id, "caption": caption},
                files={"voice": ("alert.mp3", audio_bytes, "audio/mpeg")},
            )
            if resp.status_code == 200:
                logger.debug("Telegram voice sent")
                return True
            logger.warning("Telegram sendVoice failed: status=%s body=%s", resp.status_code, resp.text[:200])
            return False
        except Exception as exc:
            logger.warning("Telegram sendVoice error: %s", exc)
            return False

    async def send_photo(self, image_bytes: bytes, caption: str) -> bool:
        """Send a photo via Telegram sendPhoto."""
        if not self._enabled:
            logger.debug("Telegram disabled, skipping photo")
            return False
        try:
            resp = await self._client.post(
                f"{self._base_url}/sendPhoto",
                data={"chat_id": self._chat_id, "caption": caption},
                files={"photo": ("incident_report.png", image_bytes, "image/png")},
            )
            if resp.status_code == 200:
                logger.debug("Telegram photo sent")
                return True
            logger.warning("Telegram sendPhoto failed: status=%s body=%s", resp.status_code, resp.text[:200])
            return False
        except Exception as exc:
            logger.warning("Telegram sendPhoto error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # High-level notification methods
    # ------------------------------------------------------------------

    async def notify_service_down(self, service_name: str, diagnosis: dict[str, Any]) -> bool:
        """Service down: Venice narrative + TTS voice note. Falls back to text."""
        audio, caption = await generate_service_down_voice(self.venice, service_name, diagnosis)

        if audio:
            ok = await self.send_voice(audio, caption)
        else:
            confidence_pct = int(diagnosis.get("confidence", 0) * 100)
            text = (
                f"SERVICE DOWN: {service_name}\n"
                f"\n"
                f"Diagnosis: {diagnosis.get('diagnosis', 'unknown')}\n"
                f"Confidence: {confidence_pct}%\n"
                f"Action: {diagnosis.get('recommended_action', 'unknown')}\n"
                f"Reasoning: {diagnosis.get('reasoning', 'N/A')}"
            )
            ok = await self.send_message(text)

        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "service_down"})
        return ok

    async def notify_recovery_started(
        self, service_name: str, old_dseq: str | None,
    ) -> bool:
        """Recovery started: Venice TTS voice note. Falls back to text."""
        audio, caption = await generate_recovery_started_voice(self.venice, service_name, old_dseq)

        if audio:
            ok = await self.send_voice(audio, caption)
        else:
            old = f"Closing old deployment {old_dseq}." if old_dseq else "No previous deployment."
            text = (
                f"RECOVERY STARTED: {service_name}\n"
                f"\n"
                f"{old}\n"
                f"Creating new deployment on Akash network."
            )
            ok = await self.send_message(text)

        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "recovery_started"})
        return ok

    async def notify_recovery_complete(
        self, service_name: str, result: dict[str, Any],
        diagnosis: dict[str, Any] | None = None,
        detection_time: float | None = None,
    ) -> bool:
        """Recovery complete: voice note + incident card image. Falls back independently."""
        success = result.get("success", False)

        if not success:
            text = (
                f"RECOVERY FAILED: {service_name}\n"
                f"\n"
                f"Error: {result.get('error', 'unknown')}"
            )
            ok = await self.send_message(text)
            if ok:
                bus.emit("telegram_sent", {"service": service_name, "message_type": "recovery_failed"})
            return ok

        # Voice note
        audio, caption = await generate_recovery_complete_voice(self.venice, service_name, result)

        if audio:
            ok = await self.send_voice(audio, caption)
        else:
            new_dseq = result.get("new_dseq", "unknown")
            provider = result.get("provider", "unknown")
            uris = ", ".join(result.get("uris", [])) or "pending"
            text = (
                f"RECOVERY COMPLETE: {service_name}\n"
                f"\n"
                f"New DSEQ: {new_dseq}\n"
                f"URIs: {uris}\n"
                f"Provider: {provider}"
            )
            ok = await self.send_message(text)

        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "recovery_complete"})

        # Incident report card
        now = time.time()
        recovery_secs = result.get("total_time_seconds", 0)
        downtime_secs = (now - detection_time) if detection_time else recovery_secs

        def _fmt_duration(secs: float) -> str:
            secs = int(secs)
            if secs < 60:
                return f"{secs}s"
            mins = secs // 60
            remaining = secs % 60
            return f"{mins}m {remaining}s"

        new_uri = ""
        uris_list = result.get("uris", [])
        if uris_list:
            new_uri = uris_list[0]

        provider_val = result.get("provider", "N/A")
        new_dseq_val = result.get("new_dseq", "N/A")
        gseq = result.get("gseq", 1)
        oseq = result.get("oseq", 1)
        lease_id = f"{new_dseq_val}/{gseq}/{oseq}"

        incident_data = {
            "service_name": service_name,
            "detection_time": detection_time or now - downtime_secs,
            "diagnosis": diagnosis.get("diagnosis", "N/A") if diagnosis else "N/A",
            "confidence": diagnosis.get("confidence", 0) if diagnosis else 0,
            "action": diagnosis.get("recommended_action", "redeploy") if diagnosis else "redeploy",
            "old_dseq": result.get("old_dseq", "N/A"),
            "new_dseq": new_dseq_val,
            "new_uri": new_uri,
            "provider": provider_val,
            "bid_price": result.get("bid_price", "N/A"),
            "bid_denom": result.get("bid_denom", "uakt"),
            "lease_id": lease_id,
            "downtime_duration": _fmt_duration(downtime_secs),
            "recovery_duration": _fmt_duration(recovery_secs),
            "resolved_time": now,
        }

        card_bytes = generate_incident_card(incident_data)
        if card_bytes:
            card_caption = f"Incident Report: {service_name} recovered"
            card_ok = await self.send_photo(card_bytes, card_caption)
            if not card_ok:
                logger.warning("Failed to send incident card photo, sending text fallback")
                await self._send_incident_text_fallback(incident_data)
        else:
            logger.warning("Failed to generate incident card, sending text fallback")
            await self._send_incident_text_fallback(incident_data)

        return ok

    async def _send_incident_text_fallback(self, data: dict[str, Any]) -> None:
        """Send incident data as formatted text when card generation or send fails."""
        text = (
            f"INCIDENT REPORT: {data['service_name']}\n"
            f"\n"
            f"Status: RESOLVED\n"
            f"Diagnosis: {data['diagnosis']}\n"
            f"Confidence: {data['confidence']}%\n"
            f"Action: {data['action']}\n"
            f"\n"
            f"Old DSEQ: {data['old_dseq']}\n"
            f"New DSEQ: {data['new_dseq']}\n"
            f"New URI: {data['new_uri']}\n"
            f"Provider: {data['provider']}\n"
            f"Bid Price: {data['bid_price']} {data['bid_denom']}/block\n"
            f"Lease ID: {data['lease_id']}\n"
            f"\n"
            f"Downtime: {data['downtime_duration']}\n"
            f"Recovery Time: {data['recovery_duration']}\n"
            f"Resolved At: {data['resolved_time']}"
        )
        await self.send_message(text)

    async def notify_service_healthy(self, service_name: str) -> bool:
        """Simple text when service returns to healthy. No voice note."""
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        text = f"{service_name} is back to healthy. Verified at {now}."
        ok = await self.send_message(text)
        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "service_healthy"})
        return ok

    async def notify_vision_check(
        self, service_name: str, assessment: dict[str, Any],
    ) -> bool:
        """Send vision health check result as plain text."""
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        healthy = assessment.get("healthy", False)
        status_text = "Verified Healthy" if healthy else "Potential Issue Detected"
        text = (
            f"VISUAL HEALTH CHECK: {service_name}\n"
            f"\n"
            f"AI Vision Assessment: {assessment.get('assessment', 'N/A')}\n"
            f"Visual Confidence: {assessment.get('confidence', 0)}%\n"
            f"Status: {status_text}\n"
            f"Verified At: {now}\n"
            f"Model: {settings.venice_vision_model}"
        )
        ok = await self.send_message(text)
        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "vision_check"})
        return ok

    async def notify_vision_skipped(self, service_name: str, reason: str) -> bool:
        """Notify that vision verification was skipped."""
        text = f"Visual verification skipped for {service_name}: {reason}"
        ok = await self.send_message(text)
        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "vision_skipped"})
        return ok

    async def close(self) -> None:
        await self._client.aclose()
