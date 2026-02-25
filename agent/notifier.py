import logging
from typing import Any

import httpx

import agent.event_bus as bus
from agent.config import settings

logger = logging.getLogger("akashguard.notifier")


class TelegramNotifier:

    def __init__(self) -> None:
        self._base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self._chat_id = settings.telegram_chat_id
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        self._enabled = bool(settings.telegram_bot_token and settings.telegram_chat_id)
        if not self._enabled:
            logger.warning("Telegram notifier disabled — missing bot token or chat ID")

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self._enabled:
            logger.debug("telegram disabled, skipping message")
            return False
        try:
            resp = await self._client.post(
                f"{self._base_url}/sendMessage",
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
            )
            if resp.status_code == 200:
                logger.debug("telegram message sent")
                return True
            logger.warning("telegram send failed status=%s body=%s", resp.status_code, resp.text[:200])
            return False
        except Exception as exc:
            logger.warning("telegram send error: %s", exc)
            return False

    async def notify_service_down(self, service_name: str, diagnosis: dict[str, Any]) -> bool:
        confidence_pct = int(diagnosis.get("confidence", 0) * 100)
        text = (
            f"\U0001f6a8 <b>SERVICE DOWN: {service_name}</b>\n"
            f"\n"
            f"\U0001f4cb Diagnosis: {diagnosis.get('diagnosis', 'unknown')}\n"
            f"\U0001f3af Confidence: {confidence_pct}%\n"
            f"\U0001f527 Action: {diagnosis.get('recommended_action', 'unknown')}\n"
            f"\U0001f4ad Reasoning: {diagnosis.get('reasoning', 'N/A')}"
        )
        ok = await self.send_message(text)
        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "service_down"})
        return ok

    async def notify_recovery_started(
        self, service_name: str, old_dseq: str | None,
    ) -> bool:
        old = f"Closing old deployment {old_dseq}..." if old_dseq else "No previous deployment."
        text = (
            f"\u2699\ufe0f <b>RECOVERY STARTED: {service_name}</b>\n"
            f"\n"
            f"{old}\n"
            f"Creating new deployment..."
        )
        ok = await self.send_message(text)
        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "recovery_started"})
        return ok

    async def notify_recovery_complete(
        self, service_name: str, result: dict[str, Any],
    ) -> bool:
        if result.get("success"):
            uris = ", ".join(result.get("uris", [])) or "pending"
            text = (
                f"\u2705 <b>RECOVERY COMPLETE: {service_name}</b>\n"
                f"\n"
                f"\U0001f195 New DSEQ: {result.get('new_dseq', 'unknown')}\n"
                f"\U0001f310 URIs: {uris}\n"
                f"\U0001f3e2 Provider: {result.get('provider', 'unknown')}"
            )
        else:
            text = (
                f"\u274c <b>RECOVERY FAILED: {service_name}</b>\n"
                f"\n"
                f"Error: {result.get('error', 'unknown')}"
            )
        ok = await self.send_message(text)
        if ok:
            msg_type = "recovery_complete" if result.get("success") else "recovery_failed"
            bus.emit("telegram_sent", {"service": service_name, "message_type": msg_type})
        return ok

    async def notify_service_healthy(self, service_name: str) -> bool:
        text = f"\U0001f49a <b>{service_name}</b> is back to healthy"
        ok = await self.send_message(text)
        if ok:
            bus.emit("telegram_sent", {"service": service_name, "message_type": "service_healthy"})
        return ok

    async def close(self) -> None:
        await self._client.aclose()
