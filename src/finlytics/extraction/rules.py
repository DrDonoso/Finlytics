"""User-defined rule matcher — Wave 1 of the rules engine (post-LLM override).

``apply_rules`` runs AFTER the LLM extraction step.  It iterates each
transaction against the enabled rules (sorted by ``(priority, id)`` ascending,
lowest first) and, on the first match, applies the rule's actions directly to
the transaction.

Match conditions (ALL must hold):
- ``description_mode`` + ``description_value`` (always case-insensitive)
- Optional ``detail_mode`` + ``detail_value``: when both are set, the rule
  also requires ``(tx.detail or "")`` to satisfy the detail condition (AND).
  Rules without a detail condition are unchanged — backward compatible.
- ``amount_sign``, ``account_ref``, ``currency`` optional filters

Phase 2 note
------------
``skip_ai`` on a rule is intentionally NOT handled here.  That flag is a
Phase-2, pre-LLM concern (``pre_match_rules`` will scan raw text, extract
date/amount via bank-format regex, and exclude matched lines from the LLM
input).  ``apply_rules`` simply ignores it.

Boundary
--------
This module does NOT import any SQLAlchemy model.  It consumes any object
that satisfies ``RuleProtocol`` (duck-typing via ``typing.Protocol``), keeping
Banner's extraction layer independent of Shuri's persistence layer.

Tag-guard bypass
----------------
Rules are user-authored, not LLM-generated.  Tags added via ``add_tags``
intentionally bypass the LLM tag guards (``_drop_merchant_tags`` /
``_drop_category_tags`` in extractor.py).
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Iterable, Optional, Protocol, runtime_checkable

from finlytics.contracts import ExtractedTransaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol (duck-typed rule interface — no DB import)
# ---------------------------------------------------------------------------


@runtime_checkable
class RuleProtocol(Protocol):
    """Structural interface for a persisted rule.

    Any object (SQLAlchemy ORM row, dataclass, Pydantic model, …) that exposes
    these attributes satisfies the protocol.  Field names mirror Shuri's
    ``rules`` table / SQLAlchemy model exactly — do NOT rename here without a
    coordinated change with Shuri.
    """

    id: int
    name: str
    priority: int       # lower integer = evaluated first
    enabled: bool

    # Match criteria
    description_mode: str           # "contains" | "starts_with" | "exact" | "regex"
    description_value: str          # pattern / substring (case-insensitive always)
    amount_sign: Optional[str]      # "negative" | "positive" | None
    amount_min: Optional[Decimal]   # abs(tx.amount) >= amount_min when set; None = no lower bound
    amount_max: Optional[Decimal]   # abs(tx.amount) <= amount_max when set; None = no upper bound
    account_ref: Optional[str]      # None = any account
    currency: Optional[str]         # None = any currency
    # Optional detail condition — both must be set to activate (AND with description).
    # Uses the same modes as description_mode (contains/starts_with/exact/regex).
    detail_mode: Optional[str]      # None = no detail condition
    detail_value: Optional[str]     # None = no detail condition

    # Actions
    set_category: Optional[str]     # None = don't override
    set_merchant: Optional[str]     # None = don't override
    add_tags: list[str]             # empty list = no tags to add
    skip_ai: bool                   # Phase-2 concern; ignored by apply_rules


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compile_regex(rule: RuleProtocol) -> re.Pattern[str] | None:
    """Compile *rule.description_value* as a case-insensitive regex.

    Returns ``None`` (and logs a warning) on ``re.error``; the caller must
    treat ``None`` as "this rule never matches".
    """
    try:
        return re.compile(rule.description_value, re.IGNORECASE)
    except re.error as exc:
        logger.warning(
            "Rule %d (%r): invalid regex %r — rule skipped. Error: %s",
            rule.id,
            rule.name,
            rule.description_value,
            exc,
        )
        return None


def _compile_detail_regex(rule: RuleProtocol) -> re.Pattern[str] | None:
    """Compile *rule.detail_value* as a case-insensitive regex.

    Returns ``None`` (and logs a warning) on ``re.error``; the caller must
    treat ``None`` as "this detail condition never matches".
    """
    if not rule.detail_value:
        return None
    try:
        return re.compile(rule.detail_value, re.IGNORECASE)
    except re.error as exc:
        logger.warning(
            "Rule %d (%r): invalid detail regex %r — detail condition skipped. Error: %s",
            rule.id,
            rule.name,
            rule.detail_value,
            exc,
        )
        return None


def _value_matches(
    text: str,
    mode: str,
    value: str,
    compiled: re.Pattern[str] | None,
) -> bool | None:
    """Case-insensitive field matcher shared by description and detail conditions.

    Returns:
        True  — condition satisfied
        False — condition not satisfied
        None  — unknown mode (caller should log a warning and treat as no-match)
    """
    text_lower = text.lower()
    value_lower = value.lower()

    if mode == "contains":
        return value_lower in text_lower
    if mode == "starts_with":
        return text_lower.startswith(value_lower)
    if mode == "exact":
        return text_lower == value_lower
    if mode == "regex":
        if compiled is None:
            return False
        return bool(compiled.search(text))

    return None  # unknown mode


def _description_matches(
    description: str,
    rule: RuleProtocol,
    compiled_regex: re.Pattern[str] | None,
) -> bool:
    """Return True if *description* satisfies the rule's description condition."""
    result = _value_matches(
        description, rule.description_mode, rule.description_value, compiled_regex
    )
    if result is None:
        logger.warning(
            "Rule %d (%r): unknown description_mode %r — rule skipped.",
            rule.id,
            rule.name,
            rule.description_mode,
        )
        return False
    return result


def _matches(
    tx: ExtractedTransaction,
    rule: RuleProtocol,
    compiled_regex: re.Pattern[str] | None,
    compiled_detail_regex: re.Pattern[str] | None = None,
) -> bool:
    """Return True if *tx* satisfies ALL conditions of *rule*.

    Evaluates, in order:
    1. Description condition (always required)
    2. Detail condition (AND — only when rule.detail_mode and rule.detail_value are both set)
    3. amount_sign filter
    4. account_ref filter
    5. currency filter
    """
    if not _description_matches(tx.description, rule, compiled_regex):
        return False

    # Detail condition: AND-ed when both detail_mode and detail_value are present.
    if rule.detail_mode and rule.detail_value:
        detail_text = tx.detail or ""
        result = _value_matches(detail_text, rule.detail_mode, rule.detail_value, compiled_detail_regex)
        if result is None:
            logger.warning(
                "Rule %d (%r): unknown detail_mode %r — detail condition treated as no-match.",
                rule.id,
                rule.name,
                rule.detail_mode,
            )
            return False
        if not result:
            return False

    if rule.amount_sign == "negative" and tx.amount >= 0:
        return False
    if rule.amount_sign == "positive" and tx.amount <= 0:
        return False

    # Magnitude filters: compare abs(tx.amount) against optional bounds.
    if rule.amount_min is not None and abs(tx.amount) < rule.amount_min:
        return False
    if rule.amount_max is not None and abs(tx.amount) > rule.amount_max:
        return False

    if rule.account_ref is not None:
        if (tx.account_ref or "").lower() != rule.account_ref.lower():
            return False

    if rule.currency is not None:
        if (tx.currency or "").lower() != rule.currency.lower():
            return False

    return True


def _merge_tags(existing: list[str], new_tags: list[str]) -> list[str]:
    """Merge *new_tags* into *existing*, preserving order and deduplicating case-insensitively.

    Existing tags retain their original order and case.  New tags are appended
    only if no existing tag matches them case-insensitively.
    """
    seen = {t.lower() for t in existing}
    result = list(existing)
    for tag in new_tags:
        if tag.lower() not in seen:
            result.append(tag)
            seen.add(tag.lower())
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_rules(
    transactions: list[ExtractedTransaction],
    rules: Iterable[RuleProtocol],
) -> list[ExtractedTransaction]:
    """Apply user-defined rules to a list of extracted transactions (post-LLM).

    Rules are evaluated in ``(priority, id)`` ascending order (lower numbers
    first).  The **first** matching rule wins per transaction; subsequent rules
    are not evaluated for that transaction.

    Match conditions (all must hold):
    - description condition (``description_mode`` + ``description_value``,
      always case-insensitive)
    - ``amount_sign``: ``"negative"`` → ``tx.amount < 0``;
      ``"positive"`` → ``tx.amount > 0``; ``None`` → ignored
    - ``account_ref``: if set, case-insensitive equality with ``tx.account_ref``
    - ``currency``: if set, case-insensitive equality with ``tx.currency``

    Actions applied on match:
    - ``set_category`` (non-null) → ``tx.category`` overridden;
      ``tx.category_confidence`` forced to ``1.0``
    - ``set_merchant`` (non-null) → ``tx.merchant`` overridden
    - ``add_tags`` (non-empty) → merged into ``tx.tags``, deduplicated
      case-insensitively (existing order preserved, new tags appended)
    - ``tx.matched_rule_id`` and ``tx.matched_rule_name`` are always set
      on a match (used by the preview "🔗 Regla" badge)

    Disabled rules (``enabled=False``) are silently skipped.

    Unmatched transactions are returned unchanged (``matched_rule_id`` stays
    ``None``).

    NOTE: ``skip_ai`` is a Phase-2 pre-LLM concern and is NOT processed here.
    Phase 2 will introduce ``pre_match_rules()`` in a later wave.

    This function is **pure** and **synchronous** — no DB access, no network.
    The input list is not mutated; rebuilt copies are returned for each matched
    transaction.  Order is preserved.
    """
    enabled_rules = sorted(
        (r for r in rules if r.enabled),
        key=lambda r: (r.priority, r.id),
    )

    # Pre-compile regex patterns once (avoids re-compiling per transaction)
    compiled: dict[int, re.Pattern[str] | None] = {
        r.id: _compile_regex(r)
        for r in enabled_rules
        if r.description_mode == "regex"
    }
    compiled_detail: dict[int, re.Pattern[str] | None] = {
        r.id: _compile_detail_regex(r)
        for r in enabled_rules
        if r.detail_mode == "regex"
    }

    result: list[ExtractedTransaction] = []
    for tx in transactions:
        for rule in enabled_rules:
            regex_pat = compiled.get(rule.id)
            detail_pat = compiled_detail.get(rule.id)
            if not _matches(tx, rule, regex_pat, detail_pat):
                continue

            # First match — apply actions
            updates: dict = {
                "matched_rule_id": rule.id,
                "matched_rule_name": rule.name,
            }
            if rule.set_category is not None:
                updates["category"] = rule.set_category
                updates["category_confidence"] = 1.0
            if rule.set_merchant is not None:
                updates["merchant"] = rule.set_merchant
            if rule.add_tags:
                updates["tags"] = _merge_tags(tx.tags, rule.add_tags)

            tx = tx.model_copy(update=updates)
            break  # first-match wins

        result.append(tx)

    return result
