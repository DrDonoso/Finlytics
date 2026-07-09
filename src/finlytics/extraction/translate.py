"""Category name translation helper.

Translates a category name (any language) to both a canonical English label
(Title Case) and a Spanish label, using the shared OpenAI client.

Returns None — never raises — so callers (Shuri's ``get_or_create_category``)
can always fall back to storing the literal name with ``name_es = NULL``.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel

from finlytics.config import settings
from finlytics.extraction.llm_client import LLMClient, LLMError, is_llm_configured

log = logging.getLogger(__name__)

# Matches leading Unicode emoji blocks + whitespace so they are stripped
# before the label is sent to the LLM.
_EMOJI_RE = re.compile(
    r"^[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F\s]+"
)

_MAX_TOKENS = 60

_SYSTEM_PROMPT = (
    "You are a bilingual (English/Spanish) category label normalizer for a "
    "personal finance app.\n"
    "Given a short expense category name in any language, output BOTH labels:\n"
    "- name_en: English, Title Case, ≤ 3 words, concise.\n"
    "- name_es: Spanish, natural capitalization, ≤ 3 words.\n"
    "If the input is already English, name_en ≈ normalized input; "
    "name_es is the Spanish translation.\n"
    "If the input is already Spanish, name_es ≈ normalized input; "
    "name_en is the English translation.\n"
    "Strip any leading emoji or whitespace before processing."
)


class _TranslationResult(BaseModel):
    name_en: str
    name_es: str


def _strip_emoji(name: str) -> str:
    return _EMOJI_RE.sub("", name).strip()


async def translate_category_name(name: str) -> dict | None:
    """Translate *name* to ``{"name_en": ..., "name_es": ...}`` or ``None``.

    Never raises.  Returns ``None`` when:

    - *name* is empty / whitespace-only
    - LLM is not configured (missing env vars)
    - Any exception occurs (one retry on transient :exc:`LLMError`)

    Returning ``None`` lets Shuri fall back to storing the literal name
    with ``name_es = NULL`` — never blocks an import or category add.
    """
    if not name or not name.strip():
        return None
    if not is_llm_configured(settings):
        return None

    clean = _strip_emoji(name)
    if not clean:
        return None

    client = LLMClient.from_settings(settings)

    for attempt in range(2):
        try:
            result: _TranslationResult = await client.parse(
                system=_SYSTEM_PROMPT,
                user=f"Category name: {clean}",
                response_format=_TranslationResult,
                temperature=0.0,
                max_completion_tokens=_MAX_TOKENS,
            )
            return {"name_en": result.name_en, "name_es": result.name_es}
        except LLMError:
            if attempt == 0:
                log.warning("translate_category_name: transient error, retrying once")
                continue
            log.error("translate_category_name: failed after retry")
        except Exception:
            log.error("translate_category_name: unexpected error")
            break

    return None
