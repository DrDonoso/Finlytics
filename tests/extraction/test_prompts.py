"""Tests for prompt builders — no LLM calls."""

from __future__ import annotations

import pytest

from finlytics.extraction.prompts import (
    _BOLD_DETAIL_BLOCK,
    _MERCHANT_BLOCK,
    _TAG_SUGGESTION_BLOCK,
    build_system_prompt,
    build_user_prompt,
)

_SEED_TAGS = ["luz", "agua", "gas", "internet", "teléfono"]


# ---------------------------------------------------------------------------
# build_system_prompt — tag suggestion block
# ---------------------------------------------------------------------------


def test_prompt_contains_tag_suggestion_header():
    prompt = build_system_prompt("BBVA")
    assert "## Tag suggestion" in prompt


def test_prompt_contains_tag_suggestion_rules():
    prompt = build_system_prompt("BBVA")
    assert "0–3" in prompt
    assert "OPTIONAL" in prompt
    assert "PII" in prompt


def test_prompt_contains_all_seed_tags():
    prompt = build_system_prompt("BBVA")
    for tag in _SEED_TAGS:
        assert tag in prompt, f"Seed tag '{tag}' missing from system prompt"


def test_prompt_seed_tags_present_with_year():
    prompt = build_system_prompt("BBVA", statement_year=2026)
    for tag in _SEED_TAGS:
        assert tag in prompt, f"Seed tag '{tag}' missing from prompt with year"


def test_prompt_tag_block_lowercase_instruction():
    prompt = build_system_prompt("BBVA")
    assert "lowercase" in prompt


def test_prompt_tag_block_complement_instruction():
    """Tags should be described as complementing (not replacing) the category."""
    prompt = build_system_prompt("BBVA")
    assert "COMPLEMENT" in prompt or "complement" in prompt.lower()


def test_prompt_tag_cap_instruction():
    """Cap at 3 tags must be mentioned."""
    prompt = build_system_prompt("BBVA")
    assert "3" in _TAG_SUGGESTION_BLOCK


# ---------------------------------------------------------------------------
# build_system_prompt — year blocks still intact
# ---------------------------------------------------------------------------


def test_prompt_year_known_block_present_when_year_given():
    prompt = build_system_prompt("BBVA", statement_year=2025)
    assert "2025" in prompt
    assert "No statement year" not in prompt


def test_prompt_year_unknown_block_present_when_no_year():
    prompt = build_system_prompt("BBVA")
    assert "No statement year" in prompt


# ---------------------------------------------------------------------------
# build_system_prompt — account_ref injection
# ---------------------------------------------------------------------------


def test_prompt_account_ref_injected():
    prompt = build_system_prompt("Indexa Capital")
    assert "Indexa Capital" in prompt


# ---------------------------------------------------------------------------
# build_user_prompt
# ---------------------------------------------------------------------------


def test_user_prompt_contains_statement_text():
    prompt = build_user_prompt("some bank statement content")
    assert "some bank statement content" in prompt


def test_user_prompt_has_delimiters():
    prompt = build_user_prompt("tx data")
    assert "STATEMENT START" in prompt
    assert "STATEMENT END" in prompt


# ---------------------------------------------------------------------------
# build_system_prompt — merchant extraction block
# ---------------------------------------------------------------------------


def test_prompt_contains_merchant_extraction_header():
    prompt = build_system_prompt("BBVA")
    assert "## Merchant extraction" in prompt


def test_prompt_merchant_block_title_case_instruction():
    prompt = build_system_prompt("BBVA")
    assert "Title Case" in prompt


def test_prompt_merchant_block_null_guidance():
    """Prompt must tell the LLM to return null for non-merchant lines."""
    prompt = build_system_prompt("BBVA")
    assert "null" in prompt.lower()
    assert "salary" in _MERCHANT_BLOCK.lower() or "nómina" in _MERCHANT_BLOCK.lower()


def test_prompt_merchant_block_no_translation():
    """Brand names must not be translated."""
    assert "NOT translated" in _MERCHANT_BLOCK


def test_prompt_merchant_block_example_brands():
    prompt = build_system_prompt("BBVA")
    for brand in ("Amazon", "Mercadona", "Netflix", "Renfe"):
        assert brand in prompt, f"Example brand '{brand}' missing from merchant block"


def test_prompt_tag_block_forbids_merchant_names():
    """Tag block must explicitly prohibit merchant/brand/company names as tags."""
    assert "NEVER" in _TAG_SUGGESTION_BLOCK
    assert "merchant" in _TAG_SUGGESTION_BLOCK.lower()


def test_prompt_tag_block_no_tags_is_acceptable():
    """Tag block must convey that zero tags is perfectly fine."""
    assert "perfectly fine" in _TAG_SUGGESTION_BLOCK or "common" in _TAG_SUGGESTION_BLOCK


# ---------------------------------------------------------------------------
# build_system_prompt — bold/detail markup block (readable-normalization)
# ---------------------------------------------------------------------------


def test_bold_detail_block_present_in_prompt():
    prompt = build_system_prompt("BBVA")
    assert "## Bold concept" in prompt


def test_bold_detail_block_instructs_readable_normalization():
    """Block must mention normalisation / readable text — not verbatim copying."""
    block = _BOLD_DETAIL_BLOCK.lower()
    assert "normalise" in block or "normalize" in block or "readable" in block


def test_bold_detail_block_no_verbatim_copy_instruction():
    """Old 'put ONLY the bold concept' verbatim instruction must be gone."""
    assert "put ONLY the bold concept" not in _BOLD_DETAIL_BLOCK


def test_bold_detail_block_forbids_all_caps_no_space_output():
    """Block must explicitly prohibit ALL-CAPS-no-space strings in output."""
    assert "ALL-CAPS" in _BOLD_DETAIL_BLOCK or "ALL CAPS" in _BOLD_DETAIL_BLOCK.upper()


def test_bold_detail_block_describes_concept_detail_split():
    """Block must still explain the description vs detail split."""
    assert "description" in _BOLD_DETAIL_BLOCK
    assert "detail" in _BOLD_DETAIL_BLOCK


def test_bold_detail_block_forbids_double_asterisks_in_output():
    """Block must tell the LLM not to include ** in the output fields."""
    assert "**" in _BOLD_DETAIL_BLOCK  # mentions the markup format
    assert "Do NOT include" in _BOLD_DETAIL_BLOCK or "do not include" in _BOLD_DETAIL_BLOCK.lower()


def test_bold_detail_block_gives_adeudo_example():
    """The canonical ADEUDOASUCARGO example must appear with its readable form."""
    assert "ADEUDOASUCARGO" in _BOLD_DETAIL_BLOCK
    assert "Adeudo a su cargo" in _BOLD_DETAIL_BLOCK


def test_bold_detail_block_gives_additional_examples():
    """At least two further normalisation examples must be present."""
    assert "PAGOCONTARJETAENSUPERMERCADOS" in _BOLD_DETAIL_BLOCK or \
           "CASHBACKPROMOCIONCOMERCIAL" in _BOLD_DETAIL_BLOCK


def test_bold_detail_block_instructs_stable_descriptions():
    """Block must mention stability so rules can be written against descriptions."""
    block = _BOLD_DETAIL_BLOCK.lower()
    assert "stable" in block or "same" in block


def test_bold_detail_null_when_no_detail():
    """Block must state that detail is null when there is no non-bold text."""
    assert "null" in _BOLD_DETAIL_BLOCK


def test_system_prompt_has_general_readability_rule():
    """System prompt extraction rules must include a general readability instruction."""
    prompt = build_system_prompt("BBVA")
    assert "READABILITY" in prompt or "human-readable" in prompt


def test_system_prompt_readability_rule_mentions_all_caps():
    """General readability rule must reference ALL-CAPS-no-space bank encoding."""
    prompt = build_system_prompt("BBVA")
    assert "ALL-CAPS" in prompt or "ALL CAPS" in prompt.upper()
