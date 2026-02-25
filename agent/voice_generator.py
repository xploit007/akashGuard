import logging
from typing import Any

from agent.venice_client import VeniceClient

logger = logging.getLogger("akashguard.voice")

NARRATOR_SYSTEM_PROMPT = (
    "You are an infrastructure incident narrator. Given raw incident data, "
    "produce a clear one-sentence spoken summary suitable for a voice alert. "
    "No emojis. No emdashes. Professional tone. Do not use special characters. "
    "Output only the spoken sentence, nothing else."
)


async def generate_service_down_voice(
    venice: VeniceClient,
    service_name: str,
    diagnosis: dict[str, Any],
) -> tuple[bytes | None, str]:
    """Generate voice note for service down alert.

    Returns (audio_bytes_or_None, caption).
    """
    confidence_pct = int(diagnosis.get("confidence", 0) * 100)
    diag_text = diagnosis.get("diagnosis", "unknown")
    action = diagnosis.get("recommended_action", "unknown")

    # Use Venice chat completions for a polished narrative
    user_msg = (
        f"Service: {service_name}, Status: down, "
        f"Diagnosis: {diag_text}, "
        f"Confidence: {confidence_pct}%, "
        f"Action: {action}"
    )
    narrative = await venice.chat_completions(NARRATOR_SYSTEM_PROMPT, user_msg)

    if narrative:
        script = narrative
    else:
        script = (
            f"Critical alert. {service_name} is unreachable. "
            f"The AI diagnosed {diag_text} with {confidence_pct} percent confidence. "
            f"Recommended action: {action}."
        )

    caption = f"AkashGuard Alert: {service_name} is down"
    audio = await venice.tts(script)
    return audio, caption


async def generate_recovery_started_voice(
    venice: VeniceClient,
    service_name: str,
    old_dseq: str | None,
) -> tuple[bytes | None, str]:
    """Generate voice note for recovery started.

    Returns (audio_bytes_or_None, caption).
    """
    old_part = f"Closing old deployment {old_dseq}." if old_dseq else ""
    script = (
        f"Recovery initiated for {service_name}. "
        f"{old_part} "
        f"Creating new deployment on Akash network."
    ).replace("  ", " ")

    caption = f"AkashGuard: Recovery started for {service_name}"
    audio = await venice.tts(script)
    return audio, caption


async def generate_recovery_complete_voice(
    venice: VeniceClient,
    service_name: str,
    result: dict[str, Any],
) -> tuple[bytes | None, str]:
    """Generate voice note for recovery complete.

    Returns (audio_bytes_or_None, caption).
    """
    new_dseq = result.get("new_dseq", "unknown")
    provider = result.get("provider", "unknown")
    provider_short = provider[:20] if provider else "unknown"
    bid_price = result.get("bid_price", "unknown")
    bid_denom = result.get("bid_denom", "uakt")
    duration = result.get("total_time_seconds", 0)

    # Use Venice chat completions for a polished narrative
    user_msg = (
        f"Service: {service_name}, Status: recovered, "
        f"New deployment: {new_dseq}, "
        f"Provider: {provider_short}, "
        f"Bid price: {bid_price} {bid_denom}/block, "
        f"Recovery time: {duration} seconds"
    )
    narrative = await venice.chat_completions(NARRATOR_SYSTEM_PROMPT, user_msg)

    if narrative:
        script = narrative
    else:
        script = (
            f"Recovery successful. {service_name} is back online on deployment {new_dseq}. "
            f"Provider: {provider_short}. "
            f"Bid price: {bid_price}. "
            f"Total recovery time: {duration} seconds."
        )

    caption = f"AkashGuard: {service_name} recovered successfully"
    audio = await venice.tts(script)
    return audio, caption
