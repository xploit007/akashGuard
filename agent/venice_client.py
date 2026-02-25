import logging
from typing import Any

import httpx

from agent.config import settings

logger = logging.getLogger("akashguard.venice")


class VeniceClient:

    def __init__(self) -> None:
        self._base_url = settings.venice_api_base.rstrip("/")
        self._api_key = settings.venice_api_key
        self._enabled = bool(self._api_key)
        self._headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if not self._enabled:
            logger.warning("Venice client disabled: missing VENICE_API_KEY")

    async def tts(self, text: str) -> bytes | None:
        """Generate speech audio from text via Venice TTS. Returns raw audio bytes."""
        if not self._enabled:
            logger.debug("Venice disabled, skipping TTS")
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                resp = await client.post(
                    f"{self._base_url}/audio/speech",
                    headers=self._headers,
                    json={
                        "model": settings.venice_tts_model,
                        "input": text,
                        "voice": settings.venice_tts_voice,
                    },
                )
                if resp.status_code == 200:
                    audio = resp.content
                    logger.info("Venice TTS success: %d bytes", len(audio))
                    return audio
                logger.warning("Venice TTS failed: status=%s body=%s", resp.status_code, resp.text[:300])
                return None
        except Exception as exc:
            logger.error("Venice TTS error: %s", exc)
            return None

    async def chat_completions(
        self, system_prompt: str, user_message: str, max_tokens: int = 100,
    ) -> str | None:
        """Generate text via Venice chat completions. Returns the response text."""
        if not self._enabled:
            logger.debug("Venice disabled, skipping chat completions")
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers,
                    json={
                        "model": settings.venice_chat_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "max_tokens": max_tokens,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    logger.info("Venice chat completions success: %d chars", len(text))
                    return text
                logger.warning("Venice chat failed: status=%s body=%s", resp.status_code, resp.text[:300])
                return None
        except Exception as exc:
            logger.error("Venice chat completions error: %s", exc)
            return None

    async def vision(self, image_base64: str, prompt: str) -> dict[str, Any] | None:
        """Analyze an image via Venice vision model. Returns parsed JSON response."""
        if not self._enabled:
            logger.debug("Venice disabled, skipping vision")
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers,
                    json={
                        "model": settings.venice_vision_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are a health verification agent. Analyze the provided "
                                    "screenshot of a web service and determine if it appears to "
                                    "be functioning correctly. Respond ONLY with a JSON object: "
                                    '{"healthy": true/false, "assessment": "brief description '
                                    'of what you see", "confidence": 0-100}'
                                ),
                            },
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{image_base64}",
                                        },
                                    },
                                    {
                                        "type": "text",
                                        "text": prompt,
                                    },
                                ],
                            },
                        ],
                        "max_tokens": 200,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    logger.info("Venice vision success: %s", text[:200])
                    # Parse JSON from response
                    import json
                    # Strip markdown fences if present
                    clean = text
                    if clean.startswith("```"):
                        clean = clean.split("\n", 1)[-1]
                    if clean.endswith("```"):
                        clean = clean.rsplit("```", 1)[0]
                    clean = clean.strip()
                    return json.loads(clean)
                logger.warning("Venice vision failed: status=%s body=%s", resp.status_code, resp.text[:300])
                return None
        except Exception as exc:
            logger.error("Venice vision error: %s", exc)
            return None
