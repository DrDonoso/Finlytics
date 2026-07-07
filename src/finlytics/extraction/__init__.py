"""Extraction pipeline — PDF/XLSX/CSV → structured, categorized transactions."""

from finlytics.extraction.extractor import detect_statement_year, extract_transactions
from finlytics.extraction.parser import parse_statement
from finlytics.extraction.prematch import pre_match_rules
from finlytics.extraction.rules import RuleProtocol, apply_rules
from finlytics.extraction.schema import ExtractedTransaction

__all__ = [
    "detect_statement_year",
    "extract_transactions",
    "parse_statement",
    "ExtractedTransaction",
    "RuleProtocol",
    "apply_rules",
    "pre_match_rules",
]
