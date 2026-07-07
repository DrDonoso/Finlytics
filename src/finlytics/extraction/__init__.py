"""Extraction pipeline — PDF/XLSX/CSV → structured, categorized transactions."""

from finlytics.extraction.extractor import detect_statement_year, extract_transactions
from finlytics.extraction.parser import parse_statement
from finlytics.extraction.schema import ExtractedTransaction

__all__ = ["detect_statement_year", "extract_transactions", "parse_statement", "ExtractedTransaction"]
