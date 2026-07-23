"""Tests comprensivos para la derivación de contribution_events de Indexa.

Contrato:
  _derive_contribution_events(raw_net_amounts) → list[NormalizedContributionEvent]
  Cada evento: {date: YYYY-MM-DD, amount: float (firmado), cumulative: float, type: str}
  type ∈ {"contribution", "withdrawal"}

Cobertura (según la especificación del task):
  TC-1  Deltas correctos: serie {0, 2000, 4000, 17999.99} → 3 eventos con amounts/cumulatives exactos
  TC-2a Primer entry = 0.0 omitido (marcador de apertura de cuenta)
  TC-2b Primer entry NON-ZERO emitido como aportación inicial
  TC-3  RETIRADA: delta negativo → amount negativo + type="withdrawal"  ← TEST TITULAR
  TC-4  Delta cero omitido: fecha sin cambio en net_amounts → sin evento
  TC-5  net_amounts vacío → lista vacía, sin crash
  TC-6  Agregación multi-cuenta: deltas de la misma fecha sumados
  TC-7a Eventos ordenados por fecha (ASC)
  TC-7b Amounts redondeados a céntimos (2 decimales)
  TC-8  Retirada parcial en el interior de una serie
  TC-9  Validación de schema: ContributionEventOut expone todos los campos del contrato
  TC-10 Round-trip de caché: serialización/deserialización preserva contribution_events
  TC-11 Integración end-to-end: _fetch_performance + contribution_events en NormalizedPerformance
  TC-12 Multi-cuenta (proveedor): get_portfolio con dos cuentas suma deltas de la misma fecha
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_perf_data(net_amounts: dict, **extra) -> dict:
    """Construye un mock de respuesta de /performance con los net_amounts dados."""
    base = {
        "total_amount": 20000.0,
        "return": {},
        "net_amounts": net_amounts,
        "portfolios": [
            {
                "cash_amount": 0.0,
                "instruments_amount": 20000.0,
                "instruments_cost": 18000.0,
                "total_amount": 20000.0,
            }
        ],
    }
    base.update(extra)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# TC-1  DELTAS CORRECTOS
# ─────────────────────────────────────────────────────────────────────────────

def test_tc1_derive_amounts_and_cumulatives():
    """TC-1: net_amounts {20240804:0, 20240904:2000, 20241004:4000, 20241231:17999.99}
    → 3 eventos con amounts [2000, 2000, 13999.99] y cumulatives [2000, 4000, 17999.99].

    El primer entry (0.0) es el marcador de apertura de cuenta y se omite.
    """
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 2000.0,
        "20241004": 4000.0,
        "20241231": 17999.99,
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3, f"Esperados 3 eventos, obtenidos {len(events)}"

    # Evento 1
    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(2000.0)
    assert events[0].cumulative == pytest.approx(2000.0)
    assert events[0].type == "contribution"

    # Evento 2
    assert events[1].date == "2024-10-04"
    assert events[1].amount == pytest.approx(2000.0)
    assert events[1].cumulative == pytest.approx(4000.0)
    assert events[1].type == "contribution"

    # Evento 3 — delta grande: 17999.99 − 4000.00 = 13999.99
    assert events[2].date == "2024-12-31"
    assert events[2].amount == pytest.approx(13999.99)
    assert events[2].cumulative == pytest.approx(17999.99)
    assert events[2].type == "contribution"


def test_tc1_integer_net_amount_keys():
    """TC-1 variante: las claves pueden ser enteros (como devuelve Indexa en bruto)."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        20240804: 0,
        20240904: 2000,
        20241004: 4000,
        20241231: 17999.99,
    }
    events = _derive_contribution_events(raw)
    assert len(events) == 3
    assert events[2].amount == pytest.approx(13999.99)


# ─────────────────────────────────────────────────────────────────────────────
# TC-2  PRIMER ENTRY
# ─────────────────────────────────────────────────────────────────────────────

def test_tc2a_first_entry_zero_skipped():
    """TC-2a: El primer entry = 0.0 se omite; no genera ningún evento."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {"20240804": 0.0}
    events = _derive_contribution_events(raw)
    assert events == [], "El marcador de apertura (0.0) no debe generar evento alguno"


def test_tc2a_first_entry_zero_then_contributions():
    """TC-2a: La omisión de 0.0 inicial no afecta a los eventos posteriores."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {"20240804": 0.0, "20240904": 5000.0}
    events = _derive_contribution_events(raw)
    assert len(events) == 1
    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(5000.0)
    assert events[0].cumulative == pytest.approx(5000.0)
    assert events[0].type == "contribution"


def test_tc2b_first_entry_nonzero_emitted():
    """TC-2b: El primer entry NON-ZERO se emite como aportación inicial
    con amount = el propio valor acumulado (no hay prev_cumulative)."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {"20240904": 3000.0, "20241004": 5000.0}
    events = _derive_contribution_events(raw)
    assert len(events) == 2

    # Primera aportación = el valor inicial completo
    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(3000.0)
    assert events[0].cumulative == pytest.approx(3000.0)
    assert events[0].type == "contribution"

    # Segunda aportación = delta desde el primer valor
    assert events[1].date == "2024-10-04"
    assert events[1].amount == pytest.approx(2000.0)
    assert events[1].cumulative == pytest.approx(5000.0)
    assert events[1].type == "contribution"


# ─────────────────────────────────────────────────────────────────────────────
# TC-3  RETIRADA (WITHDRAWAL) — TEST TITULAR
# ─────────────────────────────────────────────────────────────────────────────

def test_tc3_withdrawal_headline_delta_negative():
    """TC-3 TITULAR: net_amounts que DECRECE produce un evento NEGATIVO con type="withdrawal".

    Serie: 0 → 2000 → 4000 → 3500
    Evento en 20241104: delta = 3500 − 4000 = −500 → withdrawal.
    """
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 2000.0,
        "20241004": 4000.0,
        "20241104": 3500.0,
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3

    withdrawal = events[2]
    assert withdrawal.date == "2024-11-04"
    assert withdrawal.amount == pytest.approx(-500.0), (
        f"Retirada esperada −500.0, obtenida {withdrawal.amount}"
    )
    assert withdrawal.cumulative == pytest.approx(3500.0), (
        f"Acumulado esperado 3500.0 tras la retirada, obtenido {withdrawal.cumulative}"
    )
    assert withdrawal.type == "withdrawal", (
        f"El tipo debe ser 'withdrawal' para un delta negativo, obtenido {withdrawal.type!r}"
    )


def test_tc3_withdrawal_only_event():
    """TC-3 variante: retirada en un portfolio que solo ha tenido aportaciones → type OK."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 10000.0,
        "20241004": 8000.0,   # −2000
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 2
    assert events[1].type == "withdrawal"
    assert events[1].amount == pytest.approx(-2000.0)
    assert events[1].cumulative == pytest.approx(8000.0)


def test_tc3_multiple_withdrawals():
    """TC-3 variante: múltiples retiradas consecutivas, cada una con type='withdrawal'."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 10000.0,
        "20241004": 8000.0,    # −2000
        "20241104": 6000.0,    # −2000
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3
    assert events[1].type == "withdrawal"
    assert events[1].amount == pytest.approx(-2000.0)
    assert events[1].cumulative == pytest.approx(8000.0)
    assert events[2].type == "withdrawal"
    assert events[2].amount == pytest.approx(-2000.0)
    assert events[2].cumulative == pytest.approx(6000.0)


def test_tc3_withdrawal_followed_by_contribution():
    """TC-3 variante: retirada seguida de re-aportación — tipos alternan correctamente."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 10000.0,  # contribution
        "20241004": 8000.0,   # withdrawal −2000
        "20241104": 12000.0,  # contribution +4000
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3
    assert events[0].type == "contribution"
    assert events[1].type == "withdrawal"
    assert events[2].type == "contribution"
    assert events[2].amount == pytest.approx(4000.0)
    assert events[2].cumulative == pytest.approx(12000.0)


# ─────────────────────────────────────────────────────────────────────────────
# TC-4  DELTA CERO OMITIDO
# ─────────────────────────────────────────────────────────────────────────────

def test_tc4_zero_delta_no_event():
    """TC-4: Una fecha donde net_amounts no varía no produce evento alguno."""
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 2000.0,
        "20241004": 2000.0,   # delta = 0 → omitido
        "20241104": 5000.0,   # delta = 3000
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 2, (
        f"El delta cero debe omitirse. Esperados 2 eventos, obtenidos {len(events)}"
    )
    dates = [ev.date for ev in events]
    assert "2024-10-04" not in dates, "La fecha con delta=0 no debe aparecer en ningún evento"
    assert events[0].date == "2024-09-04"
    assert events[1].date == "2024-11-04"
    assert events[1].amount == pytest.approx(3000.0)
    assert events[1].cumulative == pytest.approx(5000.0)


# ─────────────────────────────────────────────────────────────────────────────
# TC-5  NET_AMOUNTS VACÍO
# ─────────────────────────────────────────────────────────────────────────────

def test_tc5_empty_net_amounts_returns_empty():
    """TC-5: net_amounts vacío → lista vacía, sin crash ni excepción."""
    from finlytics.investments.indexa import _derive_contribution_events

    events = _derive_contribution_events({})
    assert events == [], "net_amounts vacío debe producir lista vacía"


def test_tc5_none_equivalent_empty():
    """TC-5 variante: claves con formato inválido (longitud != 8) son ignoradas, no crashean."""
    from finlytics.investments.indexa import _derive_contribution_events

    # Claves con longitud != 8 deben filtrarse
    raw = {"20240": 1000.0, "202408040000": 2000.0}
    events = _derive_contribution_events(raw)
    assert events == [], "Claves con longitud != 8 deben ignorarse"


# ─────────────────────────────────────────────────────────────────────────────
# TC-6  AGREGACIÓN MULTI-CUENTA
# ─────────────────────────────────────────────────────────────────────────────

def test_tc6_multi_account_same_date_deltas_summed_via_aggregate():
    """TC-6 via _aggregate (service): dos cuentas con eventos en la misma fecha
    → amounts sumados, cumulative recalculado.

    Cuenta A: 2024-09-04 +2000, 2024-10-04 +2000
    Cuenta B: 2024-09-04 +3000, 2024-10-04 +1000
    Resultado: 2024-09-04 +5000 (cumul=5000), 2024-10-04 +3000 (cumul=8000)
    """
    from unittest.mock import MagicMock

    from finlytics.investments.base import (
        NormalizedContributionEvent,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
    )
    from finlytics.investments.service import _aggregate

    perf_a = NormalizedPerformance(
        total_value=20000.0,
        returns=NormalizedReturns(pl=1000.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=2000.0, cumulative=2000.0, type="contribution"),
            NormalizedContributionEvent(date="2024-10-04", amount=2000.0, cumulative=4000.0, type="contribution"),
        ],
    )
    perf_b = NormalizedPerformance(
        total_value=18000.0,
        returns=NormalizedReturns(pl=800.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=3000.0, cumulative=3000.0, type="contribution"),
            NormalizedContributionEvent(date="2024-10-04", amount=1000.0, cumulative=4000.0, type="contribution"),
        ],
    )

    conn_a = MagicMock()
    conn_a.plugin_id = "indexa-capital"
    conn_b = MagicMock()
    conn_b.plugin_id = "indexa-capital"

    portfolio_a = NormalizedPortfolio(
        holdings=[], total_value=20000.0, total_invested=19000.0,
        total_gain_loss=1000.0, performance=perf_a,
    )
    portfolio_b = NormalizedPortfolio(
        holdings=[], total_value=18000.0, total_invested=17200.0,
        total_gain_loss=800.0, performance=perf_b,
    )

    result = _aggregate([(conn_a, portfolio_a), (conn_b, portfolio_b)], total_connections=2)

    events = result.contribution_events
    assert len(events) == 2, f"Esperados 2 eventos agregados, obtenidos {len(events)}"

    ev_by_date = {ev.date: ev for ev in events}

    # 2024-09-04: 2000 + 3000 = 5000
    sep = ev_by_date.get("2024-09-04")
    assert sep is not None, "Debe haber evento en 2024-09-04"
    assert sep.amount == pytest.approx(5000.0), f"Amount 2024-09-04 esperado 5000, obtenido {sep.amount}"
    assert sep.cumulative == pytest.approx(5000.0), f"Cumulative 2024-09-04 esperado 5000, obtenido {sep.cumulative}"
    assert sep.type == "contribution"

    # 2024-10-04: 2000 + 1000 = 3000; cumulative = 5000 + 3000 = 8000
    oct_ = ev_by_date.get("2024-10-04")
    assert oct_ is not None, "Debe haber evento en 2024-10-04"
    assert oct_.amount == pytest.approx(3000.0), f"Amount 2024-10-04 esperado 3000, obtenido {oct_.amount}"
    assert oct_.cumulative == pytest.approx(8000.0), f"Cumulative 2024-10-04 esperado 8000, obtenido {oct_.cumulative}"
    assert oct_.type == "contribution"


def test_tc6_multi_account_withdrawal_cancels_contribution():
    """TC-6: Un withdrawal de cuenta B puede cancelar parcialmente una aportación de cuenta A.

    Cuenta A: 2024-09-04 +2000
    Cuenta B: 2024-09-04 −500  (retirada)
    Resultado: 2024-09-04 +1500 (contribution)
    """
    from unittest.mock import MagicMock

    from finlytics.investments.base import (
        NormalizedContributionEvent,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
    )
    from finlytics.investments.service import _aggregate

    perf_a = NormalizedPerformance(
        total_value=12000.0,
        returns=NormalizedReturns(pl=500.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=2000.0, cumulative=2000.0, type="contribution"),
        ],
    )
    perf_b = NormalizedPerformance(
        total_value=9500.0,
        returns=NormalizedReturns(pl=300.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=-500.0, cumulative=9500.0, type="withdrawal"),
        ],
    )

    conn_a = MagicMock()
    conn_a.plugin_id = "indexa-capital"
    conn_b = MagicMock()
    conn_b.plugin_id = "indexa-capital"

    portfolio_a = NormalizedPortfolio(holdings=[], total_value=12000.0, total_invested=11500.0,
                                       total_gain_loss=500.0, performance=perf_a)
    portfolio_b = NormalizedPortfolio(holdings=[], total_value=9500.0, total_invested=9200.0,
                                       total_gain_loss=300.0, performance=perf_b)

    result = _aggregate([(conn_a, portfolio_a), (conn_b, portfolio_b)], total_connections=2)

    events = result.contribution_events
    assert len(events) == 1
    assert events[0].amount == pytest.approx(1500.0)  # 2000 + (−500)
    assert events[0].type == "contribution"
    assert events[0].cumulative == pytest.approx(1500.0)


def test_tc6_multi_account_opposite_amounts_produce_zero_skip():
    """TC-6 edge: Si la suma de deltas en una fecha es exactamente 0, se omite el evento."""
    from unittest.mock import MagicMock

    from finlytics.investments.base import (
        NormalizedContributionEvent,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
    )
    from finlytics.investments.service import _aggregate

    perf_a = NormalizedPerformance(
        total_value=10000.0,
        returns=NormalizedReturns(pl=0.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=2000.0, cumulative=2000.0, type="contribution"),
        ],
    )
    perf_b = NormalizedPerformance(
        total_value=10000.0,
        returns=NormalizedReturns(pl=0.0),
        contribution_events=[
            NormalizedContributionEvent(date="2024-09-04", amount=-2000.0, cumulative=8000.0, type="withdrawal"),
        ],
    )

    conn_a = MagicMock()
    conn_a.plugin_id = "indexa-capital"
    conn_b = MagicMock()
    conn_b.plugin_id = "indexa-capital"

    portfolio_a = NormalizedPortfolio(holdings=[], total_value=10000.0, total_invested=10000.0,
                                       total_gain_loss=0.0, performance=perf_a)
    portfolio_b = NormalizedPortfolio(holdings=[], total_value=10000.0, total_invested=10000.0,
                                       total_gain_loss=0.0, performance=perf_b)

    result = _aggregate([(conn_a, portfolio_a), (conn_b, portfolio_b)], total_connections=2)

    # Suma de deltas = 0 → evento omitido
    events = result.contribution_events
    assert events == [], (
        f"Deltas opuestos que se anulan (suma=0) deben omitirse. "
        f"Obtenido: {events}"
    )


async def test_tc6_multi_account_via_provider_get_portfolio():
    """TC-6 via IndexaProvider.get_portfolio: dos cuentas con misma fecha
    → contribution_events contiene el delta sumado con cumulative correcto.

    Cuenta 1: net_amounts {20240904: 2000}
    Cuenta 2: net_amounts {20240904: 3000}
    Esperado: 1 evento en 2024-09-04 con amount=5000, cumulative=5000
    """
    from finlytics.investments.indexa import IndexaProvider

    fiscal_empty = {"fiscal_results": []}

    perf_a = _make_perf_data(
        net_amounts={"20240904": 2000.0},
        total_amount=12000.0,
    )
    perf_b = _make_perf_data(
        net_amounts={"20240904": 3000.0},
        total_amount=10000.0,
    )

    # _get se invoca en este orden:
    # get_portfolio("ACC1"): fiscal_results(ACC1), performance(ACC1)
    # get_portfolio("ACC2"): fiscal_results(ACC2), performance(ACC2)
    side_effects = [fiscal_empty, perf_a, fiscal_empty, perf_b]

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    provider = IndexaProvider()
    with (
        patch("finlytics.investments.indexa._make_client", return_value=mock_cm),
        patch("finlytics.investments.indexa._get", side_effect=side_effects),
    ):
        portfolio = await provider.get_portfolio("tok", ["ACC1", "ACC2"])

    perf = portfolio.performance
    assert perf is not None, "performance debe estar presente"
    events = perf.contribution_events
    assert len(events) == 1, f"Esperado 1 evento sumado, obtenidos {len(events)}"
    ev = events[0]
    assert ev.date == "2024-09-04"
    assert ev.amount == pytest.approx(5000.0), f"Amount sumado esperado 5000, obtenido {ev.amount}"
    assert ev.cumulative == pytest.approx(5000.0)
    assert ev.type == "contribution"


# ─────────────────────────────────────────────────────────────────────────────
# TC-7  ORDENACIÓN Y REDONDEO
# ─────────────────────────────────────────────────────────────────────────────

def test_tc7a_events_sorted_by_date_ascending():
    """TC-7a: Los eventos siempre se devuelven ordenados por fecha ascendente."""
    from finlytics.investments.indexa import _derive_contribution_events

    # Pasamos el dict en un orden diferente; la función debe ordenar
    raw = {
        "20241231": 17999.99,
        "20241004": 4000.0,
        "20240804": 0.0,
        "20240904": 2000.0,
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3
    dates = [ev.date for ev in events]
    assert dates == sorted(dates), f"Eventos no están en orden ascendente: {dates}"


def test_tc7b_amounts_rounded_to_cents():
    """TC-7b: Los amounts se redondean a 2 decimales (céntimos)."""
    from finlytics.investments.indexa import _derive_contribution_events

    # 0 → 1999.995 → delta redondeado a 2000.00
    # 1999.995 → 3333.333 → delta = 1333.338 → redondeado a 1333.34
    raw = {
        "20240804": 0.0,
        "20240904": 1999.995,
        "20241004": 3333.333,
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 2
    # Primero: amount = round(1999.995, 2) = 2000.0 (Python bankero)
    assert events[0].amount == pytest.approx(round(1999.995, 2), abs=0.01)
    # Segundo: amount = round(3333.333 - 1999.995, 2)
    expected_delta = round(3333.333 - 1999.995, 2)
    assert events[1].amount == pytest.approx(expected_delta, abs=0.01)
    # Cumulative también redondeado
    assert events[1].cumulative == pytest.approx(round(3333.333, 2), abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# TC-8  RETIRADA PARCIAL EN EL INTERIOR DE SERIE
# ─────────────────────────────────────────────────────────────────────────────

def test_tc8_partial_withdrawal_midpoint():
    """TC-8: Una retirada en el interior de una serie no interrumpe el cómputo correcto
    de los eventos posteriores.

    Serie: 0 → 5000 → 3000 (−2000) → 8000 (+5000)
    """
    from finlytics.investments.indexa import _derive_contribution_events

    raw = {
        "20240804": 0.0,
        "20240904": 5000.0,
        "20241004": 3000.0,    # withdrawal −2000
        "20241104": 8000.0,    # contribution +5000
    }
    events = _derive_contribution_events(raw)

    assert len(events) == 3

    assert events[0].amount == pytest.approx(5000.0)
    assert events[0].type == "contribution"
    assert events[0].cumulative == pytest.approx(5000.0)

    assert events[1].amount == pytest.approx(-2000.0)
    assert events[1].type == "withdrawal"
    assert events[1].cumulative == pytest.approx(3000.0)

    assert events[2].amount == pytest.approx(5000.0)
    assert events[2].type == "contribution"
    assert events[2].cumulative == pytest.approx(8000.0)


# ─────────────────────────────────────────────────────────────────────────────
# TC-9  VALIDACIÓN DE SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

def test_tc9_schema_contribution_event_out_has_all_fields():
    """TC-9: ContributionEventOut expone date, amount, cumulative y type (contrato completo)."""
    from finlytics.api.schemas import ContributionEventOut

    ev = ContributionEventOut(
        date="2024-09-04",
        amount=2000.0,
        cumulative=2000.0,
        type="contribution",
    )
    assert ev.date == "2024-09-04"
    assert ev.amount == pytest.approx(2000.0)
    assert ev.cumulative == pytest.approx(2000.0)
    assert ev.type == "contribution"


def test_tc9_schema_withdrawal_event():
    """TC-9: ContributionEventOut admite amount negativo y type='withdrawal'."""
    from finlytics.api.schemas import ContributionEventOut

    ev = ContributionEventOut(
        date="2024-11-04",
        amount=-500.0,
        cumulative=3500.0,
        type="withdrawal",
    )
    assert ev.amount == pytest.approx(-500.0)
    assert ev.cumulative == pytest.approx(3500.0)
    assert ev.type == "withdrawal"


def test_tc9_portfolio_out_schema_exposes_contribution_events():
    """TC-9: InvestmentPortfolioOut incluye contribution_events=[] por defecto."""
    from finlytics.api.schemas import ContributionEventOut, InvestmentPortfolioOut

    out = InvestmentPortfolioOut(
        total_value=0.0,
        currency="EUR",
        holdings=[],
        plugins_connected=0,
    )
    # Debe tener contribution_events como lista vacía por defecto
    assert hasattr(out, "contribution_events")
    assert isinstance(out.contribution_events, list)
    assert out.contribution_events == []


def test_tc9_portfolio_out_with_events():
    """TC-9: InvestmentPortfolioOut acepta contribution_events no vacía."""
    from finlytics.api.schemas import ContributionEventOut, InvestmentPortfolioOut

    ev = ContributionEventOut(
        date="2024-09-04",
        amount=2000.0,
        cumulative=2000.0,
        type="contribution",
    )
    out = InvestmentPortfolioOut(
        total_value=2000.0,
        currency="EUR",
        holdings=[],
        plugins_connected=1,
        contribution_events=[ev],
    )
    assert len(out.contribution_events) == 1
    assert out.contribution_events[0].amount == pytest.approx(2000.0)
    assert out.contribution_events[0].cumulative == pytest.approx(2000.0)


# ─────────────────────────────────────────────────────────────────────────────
# TC-10  ROUND-TRIP DE CACHÉ
# ─────────────────────────────────────────────────────────────────────────────

def test_tc10_cache_round_trip_preserves_contribution_events():
    """TC-10: _serialize_portfolio / _deserialize_portfolio preserva contribution_events
    con todos los campos (date, amount, cumulative, type)."""
    from finlytics.investments.base import (
        NormalizedContributionEvent,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
    )
    from finlytics.investments.service import _deserialize_portfolio, _serialize_portfolio

    original = NormalizedPortfolio(
        holdings=[],
        total_value=17999.99,
        total_invested=18000.0,
        total_gain_loss=-0.01,
        performance=NormalizedPerformance(
            total_value=17999.99,
            returns=NormalizedReturns(pl=-0.01),
            contribution_events=[
                NormalizedContributionEvent(
                    date="2024-09-04",
                    amount=2000.0,
                    cumulative=2000.0,
                    type="contribution",
                ),
                NormalizedContributionEvent(
                    date="2024-10-04",
                    amount=2000.0,
                    cumulative=4000.0,
                    type="contribution",
                ),
                NormalizedContributionEvent(
                    date="2024-12-31",
                    amount=13999.99,
                    cumulative=17999.99,
                    type="contribution",
                ),
            ],
        ),
    )

    serialized = _serialize_portfolio(original)
    restored = _deserialize_portfolio(serialized)

    assert restored.performance is not None
    events = restored.performance.contribution_events
    assert len(events) == 3, f"Round-trip perdió eventos: esperados 3, obtenidos {len(events)}"

    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(2000.0)
    assert events[0].cumulative == pytest.approx(2000.0)
    assert events[0].type == "contribution"

    assert events[2].date == "2024-12-31"
    assert events[2].amount == pytest.approx(13999.99)
    assert events[2].cumulative == pytest.approx(17999.99)
    assert events[2].type == "contribution"


def test_tc10_cache_round_trip_withdrawal():
    """TC-10: El round-trip de caché preserva eventos de tipo withdrawal."""
    from finlytics.investments.base import (
        NormalizedContributionEvent,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
    )
    from finlytics.investments.service import _deserialize_portfolio, _serialize_portfolio

    original = NormalizedPortfolio(
        holdings=[],
        total_value=3500.0,
        total_invested=3500.0,
        total_gain_loss=0.0,
        performance=NormalizedPerformance(
            total_value=3500.0,
            returns=NormalizedReturns(),
            contribution_events=[
                NormalizedContributionEvent(
                    date="2024-09-04",
                    amount=4000.0,
                    cumulative=4000.0,
                    type="contribution",
                ),
                NormalizedContributionEvent(
                    date="2024-11-04",
                    amount=-500.0,
                    cumulative=3500.0,
                    type="withdrawal",
                ),
            ],
        ),
    )

    serialized = _serialize_portfolio(original)
    restored = _deserialize_portfolio(serialized)

    events = restored.performance.contribution_events
    assert len(events) == 2
    withdrawal = events[1]
    assert withdrawal.type == "withdrawal"
    assert withdrawal.amount == pytest.approx(-500.0)
    assert withdrawal.cumulative == pytest.approx(3500.0)


# ─────────────────────────────────────────────────────────────────────────────
# TC-11  INTEGRACIÓN END-TO-END (_fetch_performance)
# ─────────────────────────────────────────────────────────────────────────────

async def test_tc11_fetch_performance_returns_contribution_events():
    """TC-11: _fetch_performance con net_amounts completo produce contribution_events
    en NormalizedPerformance (integración real del pipeline)."""
    from finlytics.investments.indexa import _fetch_performance

    mock_data = _make_perf_data(
        net_amounts={
            "20240804": 0.0,
            "20240904": 2000.0,
            "20241004": 4000.0,
            "20241231": 17999.99,
        }
    )
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert hasattr(result, "contribution_events"), (
        "NormalizedPerformance debe tener el campo contribution_events"
    )
    events = result.contribution_events
    assert len(events) == 3

    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(2000.0)
    assert events[0].cumulative == pytest.approx(2000.0)
    assert events[0].type == "contribution"

    assert events[2].date == "2024-12-31"
    assert events[2].amount == pytest.approx(13999.99)
    assert events[2].cumulative == pytest.approx(17999.99)
    assert events[2].type == "contribution"


async def test_tc11_fetch_performance_withdrawal_in_events():
    """TC-11: _fetch_performance con retirada en net_amounts → contribution_events
    incluye el evento de withdrawal con amount negativo."""
    from finlytics.investments.indexa import _fetch_performance

    mock_data = _make_perf_data(
        net_amounts={
            "20240804": 0.0,
            "20240904": 2000.0,
            "20241004": 4000.0,
            "20241104": 3500.0,   # retirada −500
        }
    )
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC_W")

    events = result.contribution_events
    assert len(events) == 3

    withdrawal = events[2]
    assert withdrawal.date == "2024-11-04"
    assert withdrawal.amount == pytest.approx(-500.0), (
        f"FALLO CRÍTICO: La retirada debe tener amount=−500.0, "
        f"obtenido {withdrawal.amount}. El tipo withdrawal no está representado."
    )
    assert withdrawal.type == "withdrawal", (
        f"FALLO CRÍTICO: El tipo debe ser 'withdrawal', obtenido {withdrawal.type!r}"
    )
    assert withdrawal.cumulative == pytest.approx(3500.0)


async def test_tc11_fetch_performance_empty_net_amounts():
    """TC-11: _fetch_performance con net_amounts vacío → contribution_events vacío."""
    from finlytics.investments.indexa import _fetch_performance

    mock_data = _make_perf_data(net_amounts={})
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC_EMPTY")

    assert result.contribution_events == []


# ─────────────────────────────────────────────────────────────────────────────
# TC-12  MULTI-CUENTA (IndexaProvider.get_portfolio)
# ─────────────────────────────────────────────────────────────────────────────

async def test_tc12_provider_get_portfolio_two_accounts_merge_events():
    """TC-12: IndexaProvider.get_portfolio con dos cuentas →
    contribution_events de la misma fecha se suman correctamente.

    ACC1: net_amounts {20240804:0, 20241004:2000}
    ACC2: net_amounts {20240804:0, 20241004:3000}
    Esperado: [{2024-10-04, amount=5000, cumulative=5000, contribution}]
    """
    from finlytics.investments.indexa import IndexaProvider

    fiscal_empty = {"fiscal_results": []}
    perf_acc1 = _make_perf_data(
        net_amounts={"20240804": 0.0, "20241004": 2000.0},
        total_amount=12000.0,
    )
    perf_acc2 = _make_perf_data(
        net_amounts={"20240804": 0.0, "20241004": 3000.0},
        total_amount=10000.0,
    )

    side_effects = [fiscal_empty, perf_acc1, fiscal_empty, perf_acc2]

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    provider = IndexaProvider()
    with (
        patch("finlytics.investments.indexa._make_client", return_value=mock_cm),
        patch("finlytics.investments.indexa._get", side_effect=side_effects),
    ):
        portfolio = await provider.get_portfolio("tok", ["ACC1", "ACC2"])

    assert portfolio.performance is not None
    events = portfolio.performance.contribution_events

    assert len(events) == 1, f"Esperado 1 evento sumado, obtenidos {len(events)}: {events}"
    ev = events[0]
    assert ev.date == "2024-10-04"
    assert ev.amount == pytest.approx(5000.0), (
        f"Delta sumado esperado 5000 (2000+3000), obtenido {ev.amount}"
    )
    assert ev.cumulative == pytest.approx(5000.0)
    assert ev.type == "contribution"


async def test_tc12_provider_two_accounts_different_dates():
    """TC-12 variante: dos cuentas con fechas distintas → eventos combinados cronológicamente."""
    from finlytics.investments.indexa import IndexaProvider

    fiscal_empty = {"fiscal_results": []}
    # ACC1: aportación en sep; ACC2: aportación en oct
    perf_acc1 = _make_perf_data(
        net_amounts={"20240804": 0.0, "20240904": 2000.0},
        total_amount=12000.0,
    )
    perf_acc2 = _make_perf_data(
        net_amounts={"20240804": 0.0, "20241004": 3000.0},
        total_amount=10000.0,
    )

    side_effects = [fiscal_empty, perf_acc1, fiscal_empty, perf_acc2]

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    provider = IndexaProvider()
    with (
        patch("finlytics.investments.indexa._make_client", return_value=mock_cm),
        patch("finlytics.investments.indexa._get", side_effect=side_effects),
    ):
        portfolio = await provider.get_portfolio("tok", ["ACC1", "ACC2"])

    events = portfolio.performance.contribution_events

    assert len(events) == 2, f"Esperados 2 eventos (fechas distintas), obtenidos {len(events)}"
    dates = [ev.date for ev in events]
    assert dates == sorted(dates), "Los eventos deben estar ordenados cronológicamente"

    # sep: 2000 (solo ACC1), cumulative = 2000
    assert events[0].date == "2024-09-04"
    assert events[0].amount == pytest.approx(2000.0)
    assert events[0].cumulative == pytest.approx(2000.0)

    # oct: 3000 (solo ACC2), cumulative = 2000 + 3000 = 5000
    assert events[1].date == "2024-10-04"
    assert events[1].amount == pytest.approx(3000.0)
    assert events[1].cumulative == pytest.approx(5000.0)
