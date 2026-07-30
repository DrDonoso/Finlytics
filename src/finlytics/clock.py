"""Fecha y hora locales de la aplicación.

``date.today()`` usa la zona horaria del proceso, y el contenedor corre en UTC:
el Dockerfile no fija ``TZ`` ni la imagen base la trae. Al mismo tiempo,
``docker-compose.yml`` expone ``TIMEZONE`` y ``Settings.timezone`` la recoge,
pero ese ajuste no se usaba en ningún sitio.

El desfase importa en los recordatorios, que razonan en días naturales: con
``Europe/Madrid`` a UTC+2 en verano, entre las 00:00 y las 02:00 el contenedor
sigue creyendo que es el día anterior, así que un recordatorio de extracto o de
compra ESPP se evalúa contra la fecha equivocada.

Se centraliza aquí para que el ajuste tenga un único punto de aplicación y para
poder sustituirlo en tests sin parchear ``datetime``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from finlytics.config import settings

__all__ = ["local_timezone", "now", "today"]

# None = todavía no resuelta. No hace falta un centinela aparte porque la
# función siempre acaba asignando una zona válida (UTC en el peor caso).
_cached_zone: ZoneInfo | timezone | None = None


def local_timezone() -> ZoneInfo | timezone:
    """Zona configurada en ``TIMEZONE``, o UTC si no se puede resolver.

    Se degrada a UTC en lugar de fallar: una zona mal escrita no debe impedir
    que la aplicación arranque, y el aviso queda en el log.
    """
    global _cached_zone
    if _cached_zone is not None:
        return _cached_zone

    try:
        _cached_zone = ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        import logging

        logging.getLogger(__name__).warning(
            "TIMEZONE=%r no es una zona horaria válida; se usará UTC.",
            settings.timezone,
        )
        _cached_zone = timezone.utc
    return _cached_zone


def now() -> datetime:
    """Instante actual en la zona configurada (siempre con tzinfo)."""
    return datetime.now(local_timezone())


def today() -> date:
    """Día natural actual según la zona configurada.

    Es lo que hay que usar en cualquier lógica que hable de «hoy», «este mes» o
    «lleva N días»: son conceptos del calendario del usuario, no del reloj UTC
    del servidor.
    """
    return now().date()


def reset_cache() -> None:
    """Olvida la zona memorizada. Pensado para tests que cambian TIMEZONE."""
    global _cached_zone
    _cached_zone = None
