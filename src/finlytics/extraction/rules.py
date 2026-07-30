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

Regex engine
------------
Patterns come from the UI, so they run through the ``regex`` package rather
than the stdlib ``re``: it accepts a per-call ``timeout``, which is the only
way to stop a catastrophically-backtracking pattern.  See ``_BoundedPattern``.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable, Optional, Protocol, runtime_checkable

import regex

from finlytics.contracts import ExtractedTransaction
from finlytics.log_safety import one_line

logger = logging.getLogger(__name__)

# Generous by three or four orders of magnitude for any sane pattern: a rule
# regex over a transaction description normally resolves in microseconds.
REGEX_TIMEOUT_SECONDS = 1.0


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


class _BoundedPattern:
    """A user-authored regex that gives up instead of hanging the process.

    Rule patterns are typed into the UI, and a shape like ``(a|a)*$`` backtracks
    exponentially.  CPython holds the GIL for the whole of a regex match, so
    such a pattern does not merely stall its own import: it freezes the event
    loop, and with it every other request the app is serving.  Threads do not
    help for the same reason — only a timeout inside the engine does.

    A pattern that blows up does so on every input, and both callers evaluate it
    in a loop (once per transaction, once per statement line).  So the first
    timeout disables the pattern for the remainder of the run: a pathological
    rule costs one timeout per import, not one per line.
    """

    __slots__ = ("_field", "_gave_up", "_pattern", "_rule_id", "_rule_name")

    def __init__(self, pattern: regex.Pattern[str], rule: RuleProtocol, field: str) -> None:
        self._pattern = pattern
        self._rule_id = rule.id
        self._rule_name = rule.name
        self._field = field
        self._gave_up = False

    def search(self, text: str) -> bool:
        """Return whether the pattern matches *text*; False once it has given up."""
        if self._gave_up:
            return False
        try:
            return self._pattern.search(text, timeout=REGEX_TIMEOUT_SECONDS) is not None
        except TimeoutError:
            self._gave_up = True
            logger.warning(
                "Rule %d (%r): %s regex exceeded %.1fs on a single input — pattern "
                "disabled for the rest of this run. Simplify it to re-enable it.",
                self._rule_id,
                one_line(self._rule_name),
                self._field,
                REGEX_TIMEOUT_SECONDS,
            )
            return False


def _compile_regex(rule: RuleProtocol) -> _BoundedPattern | None:
    """Compile *rule.description_value* as a case-insensitive regex.

    Returns ``None`` (and logs a warning) on ``regex.error``; the caller must
    treat ``None`` as "this rule never matches".
    """
    try:
        compiled = regex.compile(rule.description_value, regex.IGNORECASE)
    except regex.error as exc:
        logger.warning(
            "Rule %d (%r): invalid regex %r — rule skipped. Error: %s",
            rule.id,
            one_line(rule.name),
            one_line(rule.description_value),
            exc,
        )
        return None
    return _BoundedPattern(compiled, rule, "description")


def _compile_detail_regex(rule: RuleProtocol) -> _BoundedPattern | None:
    """Compile *rule.detail_value* as a case-insensitive regex.

    Returns ``None`` (and logs a warning) on ``regex.error``; the caller must
    treat ``None`` as "this detail condition never matches".
    """
    if not rule.detail_value:
        return None
    try:
        compiled = regex.compile(rule.detail_value, regex.IGNORECASE)
    except regex.error as exc:
        logger.warning(
            "Rule %d (%r): invalid detail regex %r — detail condition skipped. Error: %s",
            rule.id,
            one_line(rule.name),
            one_line(rule.detail_value),
            exc,
        )
        return None
    return _BoundedPattern(compiled, rule, "detail")


def _value_matches(
    text: str,
    mode: str,
    value: str,
    compiled: _BoundedPattern | None,
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
        return compiled.search(text)

    return None  # unknown mode


def _description_matches(
    description: str,
    rule: RuleProtocol,
    compiled_regex: _BoundedPattern | None,
) -> bool:
    """Return True if *description* satisfies the rule's description condition."""
    result = _value_matches(
        description, rule.description_mode, rule.description_value, compiled_regex
    )
    if result is None:
        logger.warning(
            "Rule %d (%r): unknown description_mode %r — rule skipped.",
            rule.id,
            one_line(rule.name),
            one_line(rule.description_mode),
        )
        return False
    return result


def _matches(
    tx: ExtractedTransaction,
    rule: RuleProtocol,
    compiled_regex: _BoundedPattern | None,
    compiled_detail_regex: _BoundedPattern | None = None,
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
                one_line(rule.name),
                one_line(rule.detail_mode),
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
    compiled: dict[int, _BoundedPattern | None] = {
        r.id: _compile_regex(r)
        for r in enabled_rules
        if r.description_mode == "regex"
    }
    compiled_detail: dict[int, _BoundedPattern | None] = {
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
