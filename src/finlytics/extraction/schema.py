"""Shared transaction data contract — produced by the extractor, consumed by Shuri's persistence layer.

Signed-amount convention:
    negative → money out (expenses, fees, transfers out)
    positive → money in (income, refunds, transfers in)

Do NOT include dedup_hash here — Shuri computes it from this data.

``ExtractedTransaction`` is defined in ``finlytics.contracts`` (pydantic-only,
no heavy extraction dependencies) and re-exported here so that all existing
callers importing from this module continue to work unchanged.
"""

from finlytics.contracts import ExtractedTransaction

__all__ = ["ExtractedTransaction"]
