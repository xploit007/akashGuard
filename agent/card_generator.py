import io
import logging
from datetime import datetime, timezone
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("akashguard.card")

# Colors
BG_COLOR = (10, 14, 26)          # #0a0e1a
WHITE = (255, 255, 255)
LABEL_GRAY = (139, 149, 165)     # #8b95a5
GREEN = (34, 197, 94)            # #22c55e
RED = (239, 68, 68)              # #ef4444
DIVIDER_GRAY = (40, 48, 66)      # subtle divider
ACCENT_BORDER = (55, 65, 90)     # card border accent

# Layout constants
WIDTH = 800
MARGIN_X = 48
CONTENT_X = MARGIN_X
LABEL_X = MARGIN_X
VALUE_X = 280
LINE_HEIGHT = 32
SECTION_GAP = 20


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a good font, fall back gracefully."""
    candidates = [
        "DejaVuSans.ttf",
        "DejaVuSans",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _load_font_bold(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a bold font variant."""
    candidates = [
        "DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return _load_font(size)


def _truncate(text: str, max_len: int = 40) -> str:
    if not text:
        return "N/A"
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def generate_incident_card(incident_data: dict[str, Any]) -> bytes | None:
    """Generate an incident report card as PNG bytes.

    incident_data keys:
        service_name, detection_time, diagnosis, confidence, action,
        old_dseq, new_dseq, new_uri, provider, bid_price, bid_denom,
        lease_id, recovery_duration, downtime_duration, resolved_time
    """
    try:
        return _render_card(incident_data)
    except Exception as exc:
        logger.error("Failed to generate incident card: %s", exc)
        return None


def _render_card(data: dict[str, Any]) -> bytes:
    font_label = _load_font(16)
    font_value = _load_font(17)
    font_title = _load_font_bold(26)
    font_section = _load_font_bold(15)

    # Calculate height dynamically
    # Title area + 3 sections + padding
    num_rows = 15
    height = 80 + (num_rows * LINE_HEIGHT) + (3 * SECTION_GAP) + (3 * 40) + 80
    height = max(height, 750)

    img = Image.new("RGB", (WIDTH, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    y = 40

    # Title
    draw.text((MARGIN_X, y), "AKASHGUARD INCIDENT REPORT", fill=WHITE, font=font_title)
    y += 42

    # Divider line
    draw.line([(MARGIN_X, y), (WIDTH - MARGIN_X, y)], fill=DIVIDER_GRAY, width=2)
    y += 24

    # Service and Status
    draw.text((LABEL_X, y), "Service:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), str(data.get("service_name", "unknown")), fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    draw.text((LABEL_X, y), "Status:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), "RESOLVED", fill=GREEN, font=font_value)
    y += LINE_HEIGHT + SECTION_GAP

    # DETECTION section
    draw.text((LABEL_X, y), "DETECTION", fill=WHITE, font=font_section)
    y += 30

    detection_time = data.get("detection_time", "N/A")
    if isinstance(detection_time, (int, float)):
        detection_time = datetime.fromtimestamp(detection_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    draw.text((LABEL_X, y), "Time:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), str(detection_time), fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    draw.text((LABEL_X, y), "Diagnosis:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), _truncate(str(data.get("diagnosis", "N/A")), 50), fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    confidence = data.get("confidence", 0)
    if isinstance(confidence, float) and confidence <= 1.0:
        confidence = int(confidence * 100)
    draw.text((LABEL_X, y), "Confidence:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), f"{confidence}%", fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    draw.text((LABEL_X, y), "Action Taken:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), str(data.get("action", "redeploy")), fill=WHITE, font=font_value)
    y += LINE_HEIGHT + SECTION_GAP

    # RECOVERY DETAILS section
    draw.text((LABEL_X, y), "RECOVERY DETAILS", fill=WHITE, font=font_section)
    y += 30

    draw.text((LABEL_X, y), "Old DSEQ:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), str(data.get("old_dseq", "N/A")), fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    draw.text((LABEL_X, y), "New DSEQ:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), str(data.get("new_dseq", "N/A")), fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    draw.text((LABEL_X, y), "New URI:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), _truncate(str(data.get("new_uri", "N/A")), 45), fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    draw.text((LABEL_X, y), "Provider:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), _truncate(str(data.get("provider", "N/A")), 45), fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    bid_price = data.get("bid_price", "N/A")
    bid_denom = data.get("bid_denom", "uakt")
    draw.text((LABEL_X, y), "Bid Price:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), f"{bid_price} {bid_denom}/block", fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    draw.text((LABEL_X, y), "Lease ID:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), _truncate(str(data.get("lease_id", "N/A")), 45), fill=WHITE, font=font_value)
    y += LINE_HEIGHT + SECTION_GAP

    # TIMELINE section
    draw.text((LABEL_X, y), "TIMELINE", fill=WHITE, font=font_section)
    y += 30

    draw.text((LABEL_X, y), "Total Downtime:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), str(data.get("downtime_duration", "N/A")), fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    draw.text((LABEL_X, y), "Recovery Time:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), str(data.get("recovery_duration", "N/A")), fill=WHITE, font=font_value)
    y += LINE_HEIGHT

    resolved_time = data.get("resolved_time", "N/A")
    if isinstance(resolved_time, (int, float)):
        resolved_time = datetime.fromtimestamp(resolved_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    draw.text((LABEL_X, y), "Resolved At:", fill=LABEL_GRAY, font=font_label)
    draw.text((VALUE_X, y), str(resolved_time), fill=WHITE, font=font_value)
    y += LINE_HEIGHT + 20

    # Bottom divider
    draw.line([(MARGIN_X, y), (WIDTH - MARGIN_X, y)], fill=DIVIDER_GRAY, width=1)

    # Crop to actual content height
    final_height = y + 20
    img = img.crop((0, 0, WIDTH, final_height))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    logger.info("Incident card generated: %dx%d, %d bytes", WIDTH, final_height, buf.getbuffer().nbytes)
    return buf.read()
