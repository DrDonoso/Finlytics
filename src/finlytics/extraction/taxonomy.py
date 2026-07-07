"""Fixed base category taxonomy + categorization guidance for the LLM.

IMPORTANT: this list is the single source of truth for Banner's extraction layer.
Shuri seeds the DB from this exact list — do NOT modify without team alignment.
"""

from __future__ import annotations

BASE_CATEGORIES: list[str] = [
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
]

# Spanish display labels for every base category.
# MUST stay in sync with ES_LABELS in frontend/src/i18n/index.ts.
BASE_CATEGORY_ES: dict[str, str] = {
    "Groceries": "Alimentación",
    "Dining": "Restaurantes",
    "Transport": "Transporte",
    "Fuel": "Combustible",
    "Housing": "Vivienda",
    "Utilities": "Suministros",
    "Health": "Salud",
    "Insurance": "Seguros",
    "Shopping": "Compras",
    "Entertainment": "Ocio",
    "Subscriptions": "Suscripciones",
    "Travel": "Viajes",
    "Education": "Educación",
    "Income": "Ingresos",
    "Transfers": "Transferencias",
    "Investments": "Inversiones",
    "Bank Fees": "Comisiones bancarias",
    "Taxes": "Impuestos",
    "Cash/ATM": "Efectivo/Cajero",
    "Other": "Otros",
}

# Categorization rules injected verbatim into the system prompt.
# Keep this in sync with the DB seed so UI labels always match.
CATEGORIZATION_GUIDANCE = """
## Category assignment rules

You MUST assign each transaction exactly one category. Use the following base taxonomy:

{categories}

### Rules
1. Pick the **single best match** from the list above.
2. If a transaction clearly belongs to a category not in the list, you MAY propose a new
   category name. Keep it short (≤ 3 words, Title Case). Set `is_proposed_category: true`.
3. Use "Other" only as a last resort — always prefer a specific match first.
4. Salary, pensions, dividends, interest received → Income.
5. Transfers between own accounts → Transfers (not Income).
6. Mutual funds, ETF purchases, broker deposits → Investments.
7. Card fees, maintenance fees, bank commissions → Bank Fees.
8. Supermarket chains (Mercadona, Lidl, Carrefour, etc.) → Groceries (not Shopping).
9. `category_confidence`: 1.0 = certain match, 0.5 = uncertain, 0.0 = could not determine.
""".strip()


def categories_for_prompt() -> str:
    """Return a bullet list of base categories suitable for embedding in a prompt."""
    return "\n".join(f"- {cat}" for cat in BASE_CATEGORIES)
