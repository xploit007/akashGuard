import logging
from typing import Any

from agent.venice_client import VeniceClient

logger = logging.getLogger("akashguard.voice")

NARRATOR_SYSTEM_PROMPT = (
    "You are an infrastructure incident narrator for a voice alert system. "
    "Given raw incident data, produce a clear 2-3 sentence spoken summary. "
    "CRITICAL RULES: "
    "- Do NOT read any numbers, deployment IDs, addresses, hashes, or technical identifiers. "
    "- Do NOT say things like 'deployment 25692225' or 'provider akash175...' "
    "- Instead say 'a new deployment' or 'a provider on the Akash network'. "
    "- Use approximate durations like 'about three minutes' instead of exact seconds. "
    "- No emojis. No emdashes. Professional but conversational tone. "
    "- No special characters. "
    "- Output only the spoken sentences, nothing else."
)


def _human_duration(seconds: float | int) -> str:
    """Convert seconds to human-friendly spoken duration."""
    s = int(seconds)
    if s < 60:
        return f"about {s} seconds"
    mins = s // 60
    remaining = s % 60
    if remaining == 0:
        return f"about {mins} minute{'s' if mins != 1 else ''}"
    return f"about {mins} minute{'s' if mins != 1 else ''} and {remaining} seconds"


async def generate_incident_summary_voice(
    venice: VeniceClient,
    service_name: str,
    result: dict[str, Any],
    diagnosis: dict[str, Any] | None = None,
) -> tuple[bytes | None, str]:
    """Generate a single voice note summarizing the entire incident.

    This is the ONLY voice note sent per incident — at the very end after recovery.
    No numbers, no addresses, no technical IDs in the audio.

    Returns (audio_bytes_or_None, caption).
    """
    success = result.get("success", False)
    duration = result.get("total_time_seconds", 0)
    human_dur = _human_duration(duration)
    diag_text = diagnosis.get("diagnosis", "a service failure") if diagnosis else "a service failure"
    action = diagnosis.get("recommended_action", "redeploy") if diagnosis else "redeploy"

    if success:
        user_msg = (
            f"Service name: {service_name}. "
            f"What happened: The service went down. "
            f"AI diagnosis: {diag_text}. "
            f"AI decision: {action}. "
            f"Outcome: Successfully recovered. "
            f"Recovery time: {human_dur}. "
            f"The service is now back online on a new deployment with a new provider."
        )
        caption = f"AkashGuard: {service_name} recovered successfully"
    else:
        error = result.get("error", "unknown error")
        user_msg = (
            f"Service name: {service_name}. "
            f"What happened: The service went down. "
            f"AI diagnosis: {diag_text}. "
            f"AI decision: {action}. "
            f"Outcome: Recovery failed. Error: {error}. "
            f"Manual intervention may be required."
        )
        caption = f"AkashGuard: {service_name} recovery failed"

    narrative = await venice.chat_completions(NARRATOR_SYSTEM_PROMPT, user_msg)

    if not narrative:
        # Fallback — still no numbers
        if success:
            narrative = (
                f"The {service_name} service went down due to {diag_text}. "
                f"Our AI agent initiated auto-recovery on the Akash network. "
                f"The service is now back online after {human_dur}."
            )
        else:
            narrative = (
                f"The {service_name} service went down due to {diag_text}. "
                f"Our AI agent attempted auto-recovery but it failed. "
                f"Manual intervention may be required."
            )

    audio = await venice.tts(narrative)
    return audio, caption
