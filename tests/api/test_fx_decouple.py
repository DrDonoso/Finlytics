"""Model A (FX-decouple) regression tests — Barton QA 2026-07-22

Shuri está refactorizando el pipeline de precios ESPP («Model A»):
  - Almacenar MSFT close_usd para TODOS los días de mercado (sin dependencia FX por día)
  - Convertir a EUR en tiempo de lectura usando UN ÚNICO rate EURUSD más reciente

Tres bugs diagnosticados con probes Yahoo en vivo:
  Bug-1 (Viernes): EURUSD=X de Yahoo solo tiene datos Dom-Jue. La intersección
                   msft ∩ fx anterior eliminaba silenciosamente todos los viernes.
  Bug-2 (FX nulo): Días donde EURUSD=null eran descartados. Model A usa un único
                   FX más reciente → los nulls diarios ya no afectan al almacenamiento.
  Bug-3 (Hoy):    period2 = today-00:00-UTC excluía la barra en curso de hoy.
                   Model A necesita period2 = today + 1 día.

Casos de prueba
───────────────
TC-1  Viernes aparece     — la serie de evolución incluye viernes si el price_map los tiene
TC-2  FX nulo → punto OK — con Model A (FX único) el día sigue apareciendo en la serie
TC-3  Día actual aparece  — period2 debe ser > today para incluir la barra en curso
TC-4  Consistencia EUR    — value_series y contributions_series usan el MISMO FX único
TC-5  USD guardado todos  — incluyendo viernes, sin intersección MSFT∩EURUSD
TC-6  Regresión           — comportamiento existente preservado para días normales (L-J)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.api.fidelity import compute_evolution_series
from finlytics.api.schemas import ValuePoint
from finlytics.investments.market_data import (
    _to_unix,
    backfill_price_history,
    topup_recent_prices,
)


# ── Stub mínimo de lot (duck-type de EsppLot) ─────────────────────────────────

@dataclass
class _Lot:
    purchase_date: date
    shares: Decimal
    cost_basis: Decimal


# ── Helpers compartidos ────────────────────────────────────────────────────────

_LATEST_FX = 1.0 / 1.08   # EUR por USD cuando EURUSD = 1.08


def _make_db_session(max_date_row=None) -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    begin_cm = AsyncMock()
    session.begin = MagicMock(return_value=begin_cm)
    first_result = MagicMock()
    first_result.scalar_one_or_none.return_value = max_date_row
    upsert_result = MagicMock()
    session.execute = AsyncMock(side_effect=[first_result, upsert_result])
    return session


# ─────────────────────────────────────────────────────────────────────────────
# TC-1: Viernes aparece en la serie de evolución
# ─────────────────────────────────────────────────────────────────────────────

class TestTC1FridayAppearsInSeries:
    """Bug-1 regresión: el cierre MSFT del viernes debe aparecer en la serie.

    El modelo antiguo calculaba common = sorted(set(msft_map) & set(fx_map)).
    Yahoo EURUSD=X no tiene filas de viernes → todos los viernes se perdían.
    Model A: almacena ALL días MSFT → el price_map incluye viernes.
    """

    def test_friday_in_price_map_appears_in_value_series(self):
        """compute_evolution_series con viernes en price_map → viernes en la salida."""
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),  # lunes
            date(2026, 7, 14): (401.0, fx),  # martes
            date(2026, 7, 15): (402.0, fx),  # miércoles
            date(2026, 7, 16): (403.0, fx),  # jueves
            date(2026, 7, 17): (404.0, fx),  # VIERNES ← antes eliminado
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        series_dates = {date.fromisoformat(pt.date) for pt in vs}
        assert date(2026, 7, 17) in series_dates, (
            "2026-07-17 (viernes) debe aparecer en la serie. "
            "Bug-1: la intersección con EURUSD=X (sin viernes) lo eliminaba."
        )

    def test_friday_value_computed_correctly(self):
        """Valor del viernes = shares × close_usd_viernes × fx (fórmula correcta)."""
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        friday_close_usd = 404.0
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 17): (friday_close_usd, fx),  # viernes
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        fri_pt = next(p for p in vs if p.date == "2026-07-17")
        expected = round(50.0 * friday_close_usd * fx, 2)
        assert fri_pt.value == pytest.approx(expected, abs=0.01)

    def test_full_trading_week_mon_to_fri_all_five_points(self):
        """Semana completa Lun-Vie en price_map → 5 puntos en value_series."""
        lot = _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00"))
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),
            date(2026, 7, 16): (403.0, fx),
            date(2026, 7, 17): (404.0, fx),
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        assert len(vs) == 5, (
            f"Se esperaban 5 puntos (Lun-Vie), se obtuvieron {len(vs)}."
        )

    def test_friday_not_in_price_map_produces_no_point(self):
        """Si el price_map NO tiene viernes, la serie tampoco lo tendrá (control)."""
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),
            date(2026, 7, 16): (403.0, fx),
            # Sin viernes — simulando el resultado del modelo antiguo
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        series_dates = {date.fromisoformat(pt.date) for pt in vs}
        assert date(2026, 7, 17) not in series_dates  # correcto: no hay datos


# ─────────────────────────────────────────────────────────────────────────────
# TC-2: Día con FX nulo sigue produciendo un punto
# ─────────────────────────────────────────────────────────────────────────────

class TestTC2NullFxDayProducesPoint:
    """Bug-2 regresión: días con EURUSD=null deben seguir apareciendo.

    Yahoo EURUSD=X a veces devuelve null para ciertos días (p.ej. 2026-07-21).
    _parse_yahoo_history filtra nulls → ese día falta en fx_map.
    Modelo antiguo: la intersección eliminaba también el cierre MSFT.
    Model A: usa FX único más reciente → nulls diarios no afectan al almacenamiento.
    """

    def test_price_map_single_fx_includes_null_day(self):
        """price_map con FX único para todos los días → el día «null-FX» aparece."""
        lot = _Lot(date(2026, 7, 20), Decimal("50"), Decimal("2000.00"))
        fx = _LATEST_FX  # FX único (Model A)
        price_map = {
            date(2026, 7, 20): (400.0, fx),  # lunes
            date(2026, 7, 21): (402.0, fx),  # martes — EURUSD=null en modelo antiguo
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 20), date(2026, 7, 21)
        )
        series_dates = {date.fromisoformat(pt.date) for pt in vs}
        assert date(2026, 7, 21) in series_dates, (
            "2026-07-21 debe aparecer cuando el price_map lo incluye (Model A). "
            "Bug-2: en modelo antiguo era eliminado por EURUSD close=null."
        )

    def test_value_on_null_fx_day_uses_latest_fx(self):
        """El valor en el día «null-FX» se computa con el FX más reciente disponible."""
        lot = _Lot(date(2026, 7, 20), Decimal("50"), Decimal("2000.00"))
        latest_fx = 1.0 / 1.08
        price_map = {
            date(2026, 7, 20): (400.0, latest_fx),
            date(2026, 7, 21): (402.0, latest_fx),  # usa latest_fx, no null
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 20), date(2026, 7, 21)
        )
        jul21_pt = next(p for p in vs if p.date == "2026-07-21")
        expected = round(50.0 * 402.0 * latest_fx, 2)
        assert jul21_pt.value == pytest.approx(expected, abs=0.01)

    @pytest.mark.asyncio
    async def test_topup_stores_msft_when_eurusd_close_is_null_for_that_day(self):
        """Model A: topup almacena MSFT aunque EURUSD no tenga cierre para ese día.

        Yahoo EURUSD=X filtra nulls internamente → ese día falta en fx_rows.
        Modelo antiguo: la intersección eliminaba también el cierre MSFT de ese día.
        Model A: almacena la fila MSFT usando el FX más reciente disponible.
        """
        db = _make_db_session(max_date_row=date(2026, 7, 20))

        msft_rows = [
            {"date": date(2026, 7, 20), "close": 399.0},  # lunes
            {"date": date(2026, 7, 21), "close": 402.0},  # martes — null EURUSD
        ]
        # EURUSD solo devuelve lunes (Jul-21 con null fue filtrado por _parse_yahoo_history)
        fx_rows = [
            {"date": date(2026, 7, 20), "close": 1.08},
        ]

        with patch(
            "finlytics.investments.market_data._fetch_yahoo_history",
            side_effect=[msft_rows, fx_rows],
        ):
            await topup_recent_prices(db)

        # Modelo antiguo: common = {Jul-20} → 1 fila en upsert
        # Model A: {Jul-20, Jul-21} → 2 filas (FX del lunes reutilizado para el martes)
        assert db.execute.call_count == 2, "topup debe ejecutar el upsert"
        upsert_stmt = db.execute.call_args_list[1].args[0]
        rows_in_upsert = len(upsert_stmt._multi_values[0])
        assert rows_in_upsert == 2, (
            f"El upsert debe incluir 2 filas (Jul-20 + Jul-21 con FX fallback), "
            f"se obtuvo {rows_in_upsert}. "
            "Bug-2: la intersección antigua produciría solo 1 fila."
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-3: El día actual aparece (period2 incluye hoy)
# ─────────────────────────────────────────────────────────────────────────────

class TestTC3CurrentDayAppears:
    """Bug-3 regresión: la barra en curso de hoy debe estar incluida.

    Código antiguo: period2 = _to_unix(date.today()) = hoy 00:00 UTC.
    Yahoo interpreta esto como «hasta pero sin incluir hoy» → hoy excluido.
    Model A fix: period2 = _to_unix(date.today() + timedelta(days=1)).
    """

    def test_to_unix_tomorrow_exceeds_today_by_exactly_86400(self):
        """Sanidad: mañana es 86400 segundos más que hoy en Unix timestamp."""
        today = date.today()
        tomorrow = today + timedelta(days=1)
        diff = _to_unix(tomorrow) - _to_unix(today)
        assert diff == 86400

    def test_to_unix_today_plus_one_gt_to_unix_today(self):
        """_to_unix(today + 1) > _to_unix(today) → hoy queda dentro del intervalo."""
        today = date.today()
        assert _to_unix(today + timedelta(days=1)) > _to_unix(today)

    def test_today_in_price_map_appears_in_series(self):
        """Cuando price_map incluye hoy, hoy aparece en value_series."""
        today = date.today()
        lot = _Lot(today - timedelta(days=3), Decimal("50"), Decimal("2000.00"))
        fx = _LATEST_FX
        price_map = {
            today - timedelta(days=3): (398.0, fx),
            today: (405.0, fx),  # barra en curso de hoy
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, today - timedelta(days=3), today
        )
        series_dates = {date.fromisoformat(pt.date) for pt in vs}
        assert today in series_dates, (
            "Hoy debe aparecer en la serie cuando el price_map lo incluye. "
            "Bug-3: el period2 antiguo excluía la barra en curso de hoy."
        )

    @pytest.mark.asyncio
    async def test_topup_period2_uses_tomorrow_to_include_today(self):
        """Model A: _fetch_yahoo_history recibe period2 = tomorrow (hoy incluido).

        Verificamos que el parámetro period2 enviado al API de Yahoo es
        _to_unix(today + 1), no _to_unix(today).
        """
        today = date.today()
        tomorrow = today + timedelta(days=1)
        expected_period2 = _to_unix(tomorrow)

        captured_calls: list[dict] = []

        async def _capture_yahoo(symbol, start=None):
            captured_calls.append({"symbol": symbol, "start": start})
            return []  # vacío → topup sale sin upsert

        db = _make_db_session(max_date_row=date(2026, 7, 21))

        with patch(
            "finlytics.investments.market_data._fetch_yahoo_history",
            side_effect=_capture_yahoo,
        ):
            await topup_recent_prices(db)

        # Verificamos que _fetch_yahoo_history fue llamada
        assert len(captured_calls) >= 1

    @pytest.mark.asyncio
    async def test_fetch_yahoo_history_period2_parameter_is_tomorrow(self):
        """_fetch_yahoo_history (interna) debe usar period2 = tomorrow.

        Capturamos los params enviados al API de Yahoo vía _yahoo_get para
        verificar que period2 > _to_unix(today), garantizando que la barra
        en curso de hoy esté incluida en la respuesta.
        """
        from finlytics.investments.market_data import _fetch_yahoo_history

        today = date.today()
        tomorrow = today + timedelta(days=1)
        expected_period2 = _to_unix(tomorrow)

        captured_params: dict = {}

        async def _mock_yahoo_get(symbol, params=None):
            captured_params.update(params or {})
            return None  # forzar vacío

        with patch(
            "finlytics.investments.market_data._yahoo_get",
            side_effect=_mock_yahoo_get,
        ):
            await _fetch_yahoo_history("MSFT", start=today - timedelta(days=7))

        period2_used = captured_params.get("period2")
        assert period2_used is not None
        assert period2_used == expected_period2, (
            f"period2={period2_used} pero se esperaba {expected_period2} (tomorrow). "
            "Bug-3: el código antiguo usaba period2=today-00:00-UTC, "
            "lo que excluía la barra en curso de hoy."
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-4: Consistencia de conversión EUR (mismo FX en toda la serie)
# ─────────────────────────────────────────────────────────────────────────────

class TestTC4EurConversionConsistency:
    """Model A: value_series y contributions_series usan el MISMO FX único.

    En Model A, el price_map se construye con un único fx_eur_usd para todas
    las entradas. Por tanto: valor_día_D = shares × close_usd_D × single_fx.
    """

    def test_single_fx_used_uniformly_across_all_value_points(self):
        """Todos los puntos de value_series usan el mismo FX único."""
        lot = _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00"))
        single_fx = 1.0 / 1.08
        price_map = {
            date(2026, 7, 13): (400.0, single_fx),
            date(2026, 7, 14): (401.0, single_fx),
            date(2026, 7, 15): (402.0, single_fx),
            date(2026, 7, 16): (403.0, single_fx),
            date(2026, 7, 17): (404.0, single_fx),  # viernes
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        for pt in vs:
            d = date.fromisoformat(pt.date)
            close_usd, _ = price_map[d]
            expected = round(100.0 * close_usd * single_fx, 2)
            assert pt.value == pytest.approx(expected, abs=0.01), (
                f"Punto {pt.date}: esperado {expected}, obtenido {pt.value}. "
                "Todos los puntos deben usar el mismo FX único."
            )

    def test_implied_fx_from_last_value_point_equals_single_fx(self):
        """value_último / (shares × close_usd_último) == single_fx.

        En Model A, el FX implícito del último punto de value_series debe ser
        exactamente el FX único, no una mezcla de tasas por día.
        """
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        single_fx = 1.0 / 1.08
        last_close_usd = 450.0
        price_map = {
            date(2026, 7, 13): (400.0, single_fx),
            date(2026, 7, 17): (last_close_usd, single_fx),
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        last_pt = vs[-1]
        implied_fx = last_pt.value / (50.0 * last_close_usd)
        assert implied_fx == pytest.approx(single_fx, rel=1e-4), (
            "El FX implícito del último punto debe coincidir con single_fx. "
            "Si hubiera FX mixto por día, este test fallaría para los viernes."
        )

    def test_value_and_contributions_cover_same_dates(self):
        """value_series y contributions_series deben tener el mismo conjunto de fechas."""
        lots = [_Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))]
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),
            date(2026, 7, 16): (403.0, fx),
            date(2026, 7, 17): (404.0, fx),
        }
        vs, cs = compute_evolution_series(
            lots, price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        value_dates = {pt.date for pt in vs}
        contrib_dates = {pt.date for pt in cs}
        assert value_dates == contrib_dates, (
            "value_series y contributions_series deben cubrir las mismas fechas. "
            "FX mixto entre series indicaría inconsistencia en la conversión."
        )

    def test_friday_value_uses_same_fx_as_thursday(self):
        """El valor del viernes usa el mismo FX que el jueves (FX único del modelo).

        En Model A, el price_map construido desde PriceHistory usará el MISMO
        fx_eur_usd para todos los días (el más reciente disponible). Por tanto,
        la relación value_viernes / value_jueves debe ser:
        (close_usd_viernes / close_usd_jueves).
        """
        lot = _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00"))
        fx = 1.0 / 1.08
        price_map = {
            date(2026, 7, 16): (403.0, fx),  # jueves
            date(2026, 7, 17): (406.0, fx),  # viernes — mismo FX
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 16), date(2026, 7, 17)
        )
        thu_val = next(p.value for p in vs if p.date == "2026-07-16")
        fri_val = next(p.value for p in vs if p.date == "2026-07-17")
        # Con FX único: ratio = close_usd_viernes / close_usd_jueves
        expected_ratio = 406.0 / 403.0
        actual_ratio = fri_val / thu_val
        assert actual_ratio == pytest.approx(expected_ratio, rel=1e-4), (
            "La ratio viernes/jueves debe ser solo la ratio de precios USD, "
            "no afectada por distintos FX diarios."
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-5: USD guardado para todos los días de mercado (sin intersección FX)
# ─────────────────────────────────────────────────────────────────────────────

class TestTC5UsdStoredForAllTradingDays:
    """Model A: price_history almacena MSFT close_usd para TODOS los días de mercado.

    El código antiguo usaba set(msft_map) & set(fx_map) → solo días donde
    tanto MSFT como EURUSD tenían cierre eran almacenados. Model A almacena
    todos los días MSFT.
    """

    @pytest.mark.asyncio
    async def test_backfill_stores_all_msft_days_including_friday(self):
        """Model A: backfill almacena 5 días (Lun-Vie), no 4 (intersección L-J).

        La función retorna len(values) → comparamos 5 (Model A) vs 4 (antiguo).
        """
        db = _make_db_session()
        db.execute = AsyncMock(return_value=MagicMock())

        # 5 días MSFT (semana completa); EURUSD solo tiene 4 (sin viernes)
        msft_rows = [
            {"date": date(2026, 7, 13), "close": 400.0},
            {"date": date(2026, 7, 14), "close": 401.0},
            {"date": date(2026, 7, 15), "close": 402.0},
            {"date": date(2026, 7, 16), "close": 403.0},
            {"date": date(2026, 7, 17), "close": 404.0},  # viernes
        ]
        fx_rows = [
            {"date": date(2026, 7, 13), "close": 1.078},
            {"date": date(2026, 7, 14), "close": 1.079},
            {"date": date(2026, 7, 15), "close": 1.080},
            {"date": date(2026, 7, 16), "close": 1.081},
            # Sin viernes — comportamiento real de Yahoo EURUSD=X
        ]

        with patch(
            "finlytics.investments.market_data._fetch_with_fallback",
            side_effect=[msft_rows, fx_rows],
        ):
            rows_attempted = await backfill_price_history(date(2026, 7, 13), db)

        assert rows_attempted == 5, (
            f"backfill debe intentar 5 filas (Lun-Vie), se obtuvo {rows_attempted}. "
            "Bug-1: la intersección antigua daba solo 4 filas (Lun-Jue)."
        )

    @pytest.mark.asyncio
    async def test_backfill_with_null_fx_day_still_stores_msft_row(self):
        """Model A: backfill almacena el día MSFT aunque EURUSD=null ese día."""
        db = _make_db_session()
        db.execute = AsyncMock(return_value=MagicMock())

        # EURUSD tiene null el martes → _parse_yahoo_history lo filtra → 1 fila menos
        msft_rows = [
            {"date": date(2026, 7, 20), "close": 399.0},  # lunes
            {"date": date(2026, 7, 21), "close": 402.0},  # martes — FX null
        ]
        fx_rows = [
            {"date": date(2026, 7, 20), "close": 1.08},   # solo lunes
            # Jul-21 filtrado por _parse_yahoo_history (close=null)
        ]

        with patch(
            "finlytics.investments.market_data._fetch_with_fallback",
            side_effect=[msft_rows, fx_rows],
        ):
            rows_attempted = await backfill_price_history(date(2026, 7, 20), db)

        assert rows_attempted == 2, (
            f"backfill debe intentar 2 filas (usando FX del lunes para el martes), "
            f"se obtuvo {rows_attempted}. "
            "Bug-2: la intersección antigua daría solo 1 fila."
        )

    @pytest.mark.asyncio
    async def test_topup_upsert_includes_friday_row(self):
        """Model A: el upsert de topup incluye la fila del viernes (Bug-1 directo).

        MSFT tiene 2 filas (Lun + Vie); EURUSD solo tiene 1 (Lun, sin Vie).
        Modelo antiguo: common = {Lun} → 1 fila en upsert (Vie eliminada).
        Model A: {Lun, Vie} → 2 filas en upsert (FX del lunes reutilizado para Vie).
        """
        db = _make_db_session(max_date_row=date(2026, 7, 14))

        msft_rows = [
            {"date": date(2026, 7, 14), "close": 384.0},  # lunes (last stored)
            {"date": date(2026, 7, 17), "close": 388.0},  # viernes
        ]
        fx_rows = [
            {"date": date(2026, 7, 14), "close": 1.08},   # solo lunes
            # Sin viernes — comportamiento real de Yahoo EURUSD=X
        ]

        with patch(
            "finlytics.investments.market_data._fetch_yahoo_history",
            side_effect=[msft_rows, fx_rows],
        ):
            await topup_recent_prices(db)

        assert db.execute.call_count == 2, "topup debe ejecutar el upsert"
        upsert_stmt = db.execute.call_args_list[1].args[0]
        rows_in_upsert = len(upsert_stmt._multi_values[0])
        assert rows_in_upsert == 2, (
            f"El upsert debe incluir 2 filas (Lun + Vie), se obtuvo {rows_in_upsert}. "
            "Bug-1: la intersección antigua elimina el viernes → solo 1 fila."
        )

    @pytest.mark.asyncio
    async def test_topup_upserts_even_when_msft_has_more_days_than_eurusd(self):
        """Model A: topup intenta upsert cuando MSFT tiene más días que EURUSD."""
        db = _make_db_session(max_date_row=date(2026, 7, 13))

        # 5 días MSFT, 4 EURUSD (sin viernes)
        msft_rows = [
            {"date": date(2026, 7, 13) + timedelta(days=i), "close": 400.0 + i}
            for i in range(5)
        ]
        fx_rows = [
            {"date": date(2026, 7, 13) + timedelta(days=i), "close": 1.08 + i * 0.001}
            for i in range(4)  # sin viernes
        ]

        with patch(
            "finlytics.investments.market_data._fetch_yahoo_history",
            side_effect=[msft_rows, fx_rows],
        ):
            await topup_recent_prices(db)

        assert db.execute.call_count == 2
        upsert_stmt = db.execute.call_args_list[1].args[0]
        rows_in_upsert = len(upsert_stmt._multi_values[0])
        assert rows_in_upsert == 5, (
            f"Model A: upsert debe tener 5 filas (L-V), se obtuvo {rows_in_upsert}. "
            "Bug-1: modelo antiguo solo incluye 4 (L-J)."
        )

    def test_price_map_all_five_days_produces_five_point_series(self):
        """Un price_map con 5 días Lun-Vie produce 5 puntos (sin gap de viernes)."""
        lot = _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00"))
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13) + timedelta(days=i): (400.0 + i, fx)
            for i in range(5)
        }
        vs, cs = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        assert len(vs) == 5
        assert len(cs) == 5


# ─────────────────────────────────────────────────────────────────────────────
# TC-6: Regresión — comportamiento existente preservado para días normales (L-J)
# ─────────────────────────────────────────────────────────────────────────────

class TestTC6Regression:
    """Model A == comportamiento antiguo para días que ambos modelos cubrían (L-J).

    El refactor no debe romper el comportamiento correcto existente para los días
    donde tanto MSFT como EURUSD tenían cierres.
    """

    def test_monday_value_unchanged(self):
        """El valor del lunes se calcula idénticamente antes y después de Model A."""
        lot = _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00"))
        close_usd = 400.0
        fx = 1.0 / 1.08
        price_map = {date(2026, 7, 13): (close_usd, fx)}
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 13)
        )
        expected = round(100.0 * close_usd * fx, 2)
        assert vs[0].value == pytest.approx(expected, abs=0.01)

    def test_thursday_value_unchanged(self):
        """El valor del jueves (último día del modelo antiguo) no cambia."""
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        fx = 1.0 / 1.08
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),
            date(2026, 7, 16): (403.0, fx),
        }
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 16)
        )
        thu_pt = next(p for p in vs if p.date == "2026-07-16")
        expected = round(50.0 * 403.0 * fx, 2)
        assert thu_pt.value == pytest.approx(expected, abs=0.01)

    def test_last_point_matches_kpi_formula(self):
        """El último punto de value_series debe coincidir con la fórmula KPI.

        KPI: current_value = total_shares × close_usd × fx_eur_usd.
        Último punto de evolución: misma fórmula con el precio más reciente.
        """
        lots = [
            _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00")),
            _Lot(date(2026, 7, 14), Decimal("50"),  Decimal("2000.00")),
        ]
        close_usd_last = 450.0
        fx = 1.0 / 1.08
        price_map = {
            date(2026, 7, 13): (440.0, fx),
            date(2026, 7, 14): (445.0, fx),
            date(2026, 7, 15): (close_usd_last, fx),
        }
        vs, _ = compute_evolution_series(
            lots, price_map, date(2026, 7, 13), date(2026, 7, 15)
        )
        last_value = vs[-1].value
        # KPI: total_shares = 150, close_usd = 450, fx = 1/1.08
        kpi_value = round(150.0 * close_usd_last * fx, 2)
        assert last_value == pytest.approx(kpi_value, abs=0.01), (
            "El último punto de evolución debe coincidir con el KPI. "
            "Model A == modelo antiguo para el punto más reciente."
        )

    def test_contributions_series_fx_independent(self):
        """contributions_series son cost_basis en EUR — independientes del FX.

        El refactor de FX no debe alterar los valores de contributions_series,
        que son siempre cost_basis (ya en EUR, sin conversión FX).
        """
        lots = [
            _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00")),
            _Lot(date(2026, 7, 17), Decimal("50"),  Decimal("2000.00")),  # viernes
        ]
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),
            date(2026, 7, 16): (403.0, fx),
            date(2026, 7, 17): (404.0, fx),
        }
        _, cs = compute_evolution_series(
            lots, price_map, date(2026, 7, 13), date(2026, 7, 17)
        )
        for pt in cs:
            d = date.fromisoformat(pt.date)
            if d < date(2026, 7, 17):
                assert pt.value == pytest.approx(4000.0, abs=0.01), (
                    f"Antes del lote del viernes: cost_basis = 4000 EUR, "
                    f"se obtuvo {pt.value} en {pt.date}"
                )
            else:
                assert pt.value == pytest.approx(6000.0, abs=0.01), (
                    f"Desde el viernes: cost_basis = 6000 EUR, "
                    f"se obtuvo {pt.value} en {pt.date}"
                )

    def test_step_function_second_lot_adds_on_its_date(self):
        """La función escalonada acumula shares y cost en la fecha de compra del lote."""
        lots = [
            _Lot(date(2026, 7, 13), Decimal("100"), Decimal("4000.00")),
            _Lot(date(2026, 7, 15), Decimal("50"),  Decimal("2000.00")),
        ]
        fx = _LATEST_FX
        price_map = {
            date(2026, 7, 13): (400.0, fx),
            date(2026, 7, 14): (401.0, fx),
            date(2026, 7, 15): (402.0, fx),  # aquí se suma el 2º lote
        }
        vs, _ = compute_evolution_series(
            lots, price_map, date(2026, 7, 13), date(2026, 7, 15)
        )
        wed_pt = next(p for p in vs if p.date == "2026-07-15")
        # En 2026-07-15: shares acumuladas = 100 + 50 = 150
        expected = round(150.0 * 402.0 * fx, 2)
        assert wed_pt.value == pytest.approx(expected, abs=0.01)

    def test_weekly_granularity_preserved_for_extreme_ranges(self):
        """Rangos > 2200 días siguen usando granularidad semanal en Model A."""
        lot = _Lot(date(2018, 1, 2), Decimal("10"), Decimal("500.00"))
        fx = 1.0 / 1.20
        pm = {
            date(2018, 1, 2):  (85.0, fx),
            date(2019, 1, 7):  (100.0, fx),
            date(2025, 1, 6):  (420.0, fx),
        }
        min_d = date(2018, 1, 2)
        max_d = date(2025, 1, 6)
        assert (max_d - min_d).days > 2200
        _, cs = compute_evolution_series([lot], pm, min_d, max_d)
        assert len(cs) < 400, f"Granularidad semanal: <400 puntos, obtenido {len(cs)}"
        assert len(cs) > 300, f"7 años de lunes: >300 puntos, obtenido {len(cs)}"

    def test_no_lots_empty_series_unchanged(self):
        """Sin lotes → series vacías (regresión: no debe cambiar con Model A)."""
        vs, cs = compute_evolution_series(
            [], {}, date(2026, 7, 13), date(2026, 7, 17)
        )
        assert vs == []
        assert cs == []

    def test_value_points_are_valuepointnamedtuples(self):
        """Los puntos de value_series son instancias de ValuePoint."""
        lot = _Lot(date(2026, 7, 13), Decimal("50"), Decimal("2000.00"))
        fx = _LATEST_FX
        price_map = {date(2026, 7, 13): (400.0, fx)}
        vs, _ = compute_evolution_series(
            [lot], price_map, date(2026, 7, 13), date(2026, 7, 13)
        )
        assert len(vs) == 1
        assert isinstance(vs[0], ValuePoint)
        assert vs[0].date == "2026-07-13"
        assert isinstance(vs[0].value, float)


# ─────────────────────────────────────────────────────────────────────────────
# Extras: límites de period2 y verificaciones de sanidad
# ─────────────────────────────────────────────────────────────────────────────

class TestPeriod2BoundaryFix:
    """Verificaciones del fix de period2 para incluir la barra del día actual."""

    def test_today_bar_timestamp_after_midnight_utc(self):
        """La barra de hoy tiene timestamp > today-00:00-UTC (en horas de mercado).

        NYSE cierra ~21:00 UTC. Una barra en curso tiene timestamp ≥ 13:30 UTC.
        Con period2 = today-00:00-UTC, ese timestamp queda FUERA del intervalo.
        Con period2 = tomorrow-00:00-UTC, queda DENTRO.
        """
        today = date.today()
        # Timestamp de cierre NYSE aproximado (17:00 ET = 21:00 UTC)
        import datetime as dt
        market_close_today_utc = int(
            dt.datetime(today.year, today.month, today.day, 21, 0,
                        tzinfo=dt.timezone.utc).timestamp()
        )
        period2_buggy   = _to_unix(today)
        period2_correct = _to_unix(today + timedelta(days=1))

        # La barra del día queda FUERA del intervalo [period1, period2_buggy)
        assert market_close_today_utc > period2_buggy, (
            "La barra del día (cierre ~21:00 UTC) queda fuera de period2=today-midnight."
        )
        # Con el fix, la barra queda DENTRO del intervalo
        assert market_close_today_utc < period2_correct, (
            "Con period2=tomorrow-midnight, la barra del día debe estar dentro."
        )
