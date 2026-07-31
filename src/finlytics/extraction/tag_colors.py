"""Tag color suggestion helper.

Suggests a visually distinct hex color (#RRGGBB) for each input tag name,
using the shared LLM client.  Mirrors the ``translate_category_name`` pattern
in ``translate.py``.

Returns ``None`` — never raises — so callers can always fall back to a static
colour palette when the LLM is unavailable or returns unexpected output.
"""

from __future__ import annotations

import logging
import re
from typing import List

from pydantic import BaseModel

from finlytics.config import settings
from finlytics.extraction.llm_client import LLMClient, LLMError, is_llm_configured

log = logging.getLogger(__name__)

# Strict #RRGGBB validation — rejects shorthand (#RGB), bare hex, CSS names, etc.
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

_MAX_TOKENS = 200

_SYSTEM_PROMPT = (
    "You are a UI colour designer for a personal finance app.\n"
    "Given a list of Spanish expense tags, assign each a visually distinct "
    "hex colour (#RRGGBB).\n"
    "Rules:\n"
    "- Prefer semantically sensible colours where obvious: "
    "agua→#3b82f6 (blue), luz→#eab308 (yellow), gas→#f97316 (orange), "
    "teléfono→#22c55e (green), internet→#8b5cf6 (purple).\n"
    "- All colours must be visually distinct from each other.\n"
    "- Use pleasant, mid-range saturation — not too dark, not too pale.\n"
    "- Return EVERY tag from the input — no omissions.\n"
    "- Each colour value must be exactly '#RRGGBB' (6 hex digits)."
)


class _TagColor(BaseModel):
    tag: str
    color: str


class _ColorResult(BaseModel):
    colors: List[_TagColor]


def _is_valid_hex(color: str) -> bool:
    return bool(_HEX_RE.match(color))


async def suggest_tag_colors(tag_names: list[str]) -> dict[str, str] | None:
    """Suggest a hex colour for each tag name.

    Returns a dict mapping every input tag → ``#RRGGBB``, or ``None`` when:

    - *tag_names* is empty
    - LLM is not configured (missing env vars)
    - Any error occurs (one retry on transient :exc:`LLMError`)
    - Any returned colour is not a valid ``#RRGGBB`` hex, or any input tag is
      absent from the model response

    Never raises.  Shuri / the frontend falls back to a static palette on
    ``None``.
    """
    if not tag_names:
        return None
    if not is_llm_configured(settings):
        return None

    tag_list = ", ".join(tag_names)
    client = LLMClient.from_settings(settings)

    for attempt in range(2):
        try:
            result: _ColorResult = await client.parse(
                system=_SYSTEM_PROMPT,
                user=f"Tags: [{tag_list}]",
                response_format=_ColorResult,
                max_completion_tokens=_MAX_TOKENS,
            )
            color_map = {item.tag: item.color for item in result.colors}
            # Validate every input tag is present with a valid #RRGGBB colour.
            for tag in tag_names:
                hex_val = color_map.get(tag)
                if hex_val is None or not _is_valid_hex(hex_val):
                    log.warning(
                        "suggest_tag_colors: missing or invalid colour for tag %r", tag
                    )
                    return None
            # Return only the requested tags (discard any extras the model added).
            return {tag: color_map[tag] for tag in tag_names}
        except LLMError:
            if attempt == 0:
                log.warning("suggest_tag_colors: transient error, retrying once")
                continue
            log.error("suggest_tag_colors: failed after retry")
        except Exception:
            log.error("suggest_tag_colors: unexpected error")
            break

    return None
