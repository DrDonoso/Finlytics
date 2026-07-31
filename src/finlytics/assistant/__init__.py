"""Finance assistant — a read-only, tool-calling agent over the user's own data.

The model never sees the database and never writes SQL.  It picks from a fixed
catalogue of typed tools (``tools.py``) whose executors delegate to the same
``finlytics.db.queries`` layer that renders the dashboards, so a chat answer can
never disagree with the UI.

Modules
-------
context      – compact "what data exists" header injected into the system prompt
projections  – deterministic compound-interest engine (no LLM, no I/O)
prompts      – version-controlled system prompt
service      – the bounded agent loop, yielding stream events
tools        – the read-only tool registry
"""
