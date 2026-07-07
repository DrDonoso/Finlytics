"""Tests for base taxonomy completeness and prompt helpers."""

from finlytics.extraction.taxonomy import BASE_CATEGORIES, categories_for_prompt

_REQUIRED = {
    "Groceries",
    "Dining",
    "Transport",
    "Fuel",
    "Housing",
    "Utilities",
    "Health",
    "Insurance",
    "Shopping",
    "Entertainment",
    "Subscriptions",
    "Travel",
    "Education",
    "Income",
    "Transfers",
    "Investments",
    "Bank Fees",
    "Taxes",
    "Cash/ATM",
    "Other",
}


def test_taxonomy_has_all_required_categories():
    assert _REQUIRED == set(BASE_CATEGORIES)


def test_no_duplicate_categories():
    assert len(BASE_CATEGORIES) == len(set(BASE_CATEGORIES))


def test_category_count():
    assert len(BASE_CATEGORIES) == 20


def test_categories_for_prompt_contains_all():
    prompt_text = categories_for_prompt()
    for cat in BASE_CATEGORIES:
        assert cat in prompt_text


def test_categories_for_prompt_uses_bullets():
    prompt_text = categories_for_prompt()
    assert "- Groceries" in prompt_text
    assert "- Other" in prompt_text
