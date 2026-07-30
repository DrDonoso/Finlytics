"""Tests de la fecha local de la aplicación.

``TIMEZONE`` estaba declarado en la configuración y expuesto en
``docker-compose.yml``, pero no se usaba en ningún sitio: todo el código llamaba
a ``date.today()``, que en el contenedor devuelve la fecha UTC porque ni el
Dockerfile ni la imagen base fijan ``TZ``.

El desfase sólo se nota en la franja horaria en la que el día natural local y el
UTC no coinciden, así que es un fallo que aparece de madrugada y desaparece solo
— exactamente el tipo de cosa que conviene dejar fijada con tests.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from finlytics import clock


@pytest.fixture(autouse=True)
def _clear_zone_cache():
    """La zona se memoriza; los tests que la cambian necesitan partir de cero."""
    clock.reset_cache()
    yield
    clock.reset_cache()


# ── Resolución de la zona ────────────────────────────────────────────────────

def test_uses_the_configured_timezone(monkeypatch):
    monkeypatch.setattr(clock.settings, "timezone", "Europe/Madrid")

    assert clock.local_timezone() == ZoneInfo("Europe/Madrid")


def test_falls_back_to_utc_on_an_invalid_timezone(monkeypatch):
    """Una zona mal escrita no debe impedir que la aplicación arranque."""
    monkeypatch.setattr(clock.settings, "timezone", "Marte/Olympus_Mons")

    assert clock.local_timezone() is timezone.utc


def test_now_always_carries_tzinfo(monkeypatch):
    monkeypatch.setattr(clock.settings, "timezone", "Europe/Madrid")

    assert clock.now().tzinfo is not None


# ── El fallo que motiva el módulo ────────────────────────────────────────────

def test_local_date_differs_from_utc_in_the_early_hours(monkeypatch):
    """A la 01:00 en Madrid (verano) en UTC todavía es el día anterior.

    Es la situación real que corregía este cambio: el contenedor corre en UTC,
    así que durante esas horas los recordatorios se evaluaban contra el día
    equivocado.
    """
    madrid = ZoneInfo("Europe/Madrid")
    instant = datetime(2026, 7, 30, 1, 0, tzinfo=madrid)   # 2026-07-29T23:00Z

    assert instant.astimezone(timezone.utc).date() == date(2026, 7, 29)
    assert instant.astimezone(madrid).date() == date(2026, 7, 30)


def test_today_follows_the_configured_timezone(monkeypatch):
    """La fecha devuelta cambia con TIMEZONE, no con el reloj del servidor."""
    instant = datetime(2026, 7, 29, 23, 30, tzinfo=timezone.utc)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            return instant.astimezone(tz) if tz else instant

    monkeypatch.setattr(clock, "datetime", _FrozenDatetime)

    monkeypatch.setattr(clock.settings, "timezone", "Europe/Madrid")
    clock.reset_cache()
    assert clock.today() == date(2026, 7, 30)   # ya es el día 30 en Madrid

    monkeypatch.setattr(clock.settings, "timezone", "UTC")
    clock.reset_cache()
    assert clock.today() == date(2026, 7, 29)   # en UTC sigue siendo el 29


def test_today_matches_a_plain_date_today_when_configured_as_utc(monkeypatch):
    """Con TIMEZONE=UTC el comportamiento coincide con el anterior.

    Sirve de red: quien tuviera el contenedor en UTC y le funcionara bien no
    debería notar ningún cambio.
    """
    monkeypatch.setattr(clock.settings, "timezone", "UTC")

    assert clock.today() == datetime.now(timezone.utc).date()
