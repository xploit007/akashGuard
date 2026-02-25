import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

import agent.event_bus as bus
from agent.config import settings
from agent.venice_client import VeniceClient
from agent.voice_generator import generate_incident_summary_voice
from agent.card_generator import generate_incident_card

logger = logging.getLogger("akashguard.notifier")


def _fmt_duration(secs: float) -> str:
    """Human-readable duration for text messages."""
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    remaining = secs % 60
    return f"{mins}m {remaining}s"


def _fmt_price(amount: str, denom: str) -> str:
    """Round bid price to 4 decimals, replace IBC hash with AKT."""
    try:
        val = float(amount)
        formatted = f"{val:.4f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        formatted = str(amount)
    label = "AKT" if (denom and denom.startswith("ibc/")) else (denom or "AKT")
    return f"{formatted} {label}"


def _short_provider(provider: str) -> str:
    """Truncate provider address to first 12 chars."""
    if not provider:
        return "N/A"
    return provider[:12] + "..." if len(provider) > 12 else provider


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
    # High-level notification methods — NEW FLOW
    #
    # 1. notify_first_failure    — first health check fails (text)
    # 2. notify_threshold_hit    — 3 consecutive failures (text)
    # 3. notify_llm_decision     — what LLM decided (text)
    # 4. notify_recovery_complete — report card + voice overview (text+image+voice)
    # ------------------------------------------------------------------

    async def notify_first_failure(self, service_name: str, error: str) -> bool:
        """Notification #1: First health check failure. Text only."""
        text = f"AkashGuard: {service_name} health check failed. Monitoring..."
        ok = await self.send_message(text)
        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "first_failure"})
        return ok

    async def notify_threshold_hit(
        self, service_name: str, failures: int, threshold: int,
    ) -> bool:
        """Notification #2: Consecutive failure threshold hit. Text only."""
        text = (
            f"AkashGuard: {service_name} has failed {failures} consecutive health checks. "
            f"Consulting AI for diagnosis..."
        )
        ok = await self.send_message(text)
        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "threshold_hit"})
        return ok

    async def notify_llm_decision(
        self, service_name: str, diagnosis: dict[str, Any],
    ) -> bool:
        """Notification #3: LLM diagnosis result. Text only."""
        confidence_pct = int(diagnosis.get("confidence", 0) * 100)
        text = (
            f"AkashGuard AI Decision for {service_name}:\n"
            f"\n"
            f"Diagnosis: {diagnosis.get('diagnosis', 'unknown')}\n"
            f"Confidence: {confidence_pct}%\n"
            f"Action: {diagnosis.get('recommended_action', 'unknown')}"
        )
        ok = await self.send_message(text)
        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "llm_decision"})
        return ok

    async def notify_recovery_complete(
        self, service_name: str, result: dict[str, Any],
        diagnosis: dict[str, Any] | None = None,
        detection_time: float | None = None,
    ) -> bool:
        """Notification #4: Recovery complete — incident card + voice overview.

        Sends:
        - Incident report card (image)
        - ONE voice note summarizing the incident (no numbers in audio)
        """
        success = result.get("success", False)

        if not success:
            text = (
                f"AkashGuard: Recovery FAILED for {service_name}\n"
                f"\n"
                f"Error: {result.get('error', 'unknown')}"
            )
            ok = await self.send_message(text)
            if ok:
                bus.emit("telegram_sent", {"service": service_name, "message_type": "recovery_failed"})

            # Still send voice note for failed recovery
            audio, caption = await generate_incident_summary_voice(
                self.venice, service_name, result, diagnosis,
            )
            if audio:
                await self.send_voice(audio, caption)
            return ok

        # --- Successful recovery ---

        # Build incident data for the card
        now = time.time()
        recovery_secs = result.get("total_time_seconds", 0)
        downtime_secs = (now - detection_time) if detection_time else recovery_secs

        new_uri = ""
        uris_list = result.get("uris", [])
        if uris_list:
            new_uri = uris_list[0]

        provider_val = result.get("provider", "N/A")
        new_dseq_val = result.get("new_dseq", "N/A")
        gseq = result.get("gseq", 1)
        oseq = result.get("oseq", 1)
        lease_id = f"{new_dseq_val}/{gseq}/{oseq}"

        bid_price_raw = result.get("bid_price", "N/A")
        bid_denom_raw = result.get("bid_denom", "uakt")

        incident_data = {
            "service_name": service_name,
            "detection_time": detection_time or now - downtime_secs,
            "diagnosis": diagnosis.get("diagnosis", "N/A") if diagnosis else "N/A",
            "confidence": diagnosis.get("confidence", 0) if diagnosis else 0,
            "action": diagnosis.get("recommended_action", "redeploy") if diagnosis else "redeploy",
            "old_dseq": result.get("old_dseq", "N/A"),
            "new_dseq": new_dseq_val,
            "new_uri": new_uri,
            "provider": _short_provider(provider_val),
            "bid_price": _fmt_price(bid_price_raw, bid_denom_raw),
            "lease_id": lease_id,
            "downtime_duration": _fmt_duration(downtime_secs),
            "recovery_duration": _fmt_duration(recovery_secs),
            "resolved_time": now,
        }

        # Send incident card (image)
        card_bytes = generate_incident_card(incident_data)
        if card_bytes:
            card_caption = f"Incident Report: {service_name} recovered"
            card_ok = await self.send_photo(card_bytes, card_caption)
            if not card_ok:
                logger.warning("Failed to send incident card, sending text fallback")
                await self._send_incident_text_fallback(incident_data)
        else:
            logger.warning("Failed to generate incident card, sending text fallback")
            await self._send_incident_text_fallback(incident_data)

        bus.emit("telegram_sent", {"service": service_name, "message_type": "recovery_complete"})

        # Send ONE voice note — the audio overview (no numbers)
        audio, caption = await generate_incident_summary_voice(
            self.venice, service_name, result, diagnosis,
        )
        if audio:
            await self.send_voice(audio, caption)
        else:
            logger.warning("Failed to generate voice overview for %s", service_name)

        return True

    async def _send_incident_text_fallback(self, data: dict[str, Any]) -> None:
        """Send incident data as formatted text when card generation or send fails."""
        text = (
            f"INCIDENT REPORT: {data['service_name']}\n"
            f"\n"
            f"Status: RESOLVED\n"
            f"Diagnosis: {data['diagnosis']}\n"
            f"Confidence: {int(data['confidence'] * 100) if isinstance(data['confidence'], float) and data['confidence'] <= 1 else data['confidence']}%\n"
            f"Action: {data['action']}\n"
            f"\n"
            f"New DSEQ: {data['new_dseq']}\n"
            f"New URI: {data['new_uri']}\n"
            f"Provider: {data['provider']}\n"
            f"Bid Price: {data['bid_price']}\n"
            f"\n"
            f"Downtime: {data['downtime_duration']}\n"
            f"Recovery Time: {data['recovery_duration']}"
        )
        await self.send_message(text)

    async def close(self) -> None:
        await self._client.aclose()
