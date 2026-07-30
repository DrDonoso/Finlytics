"""Límite de intentos de autenticación.

Sin esto, ``POST /api/auth/login`` acepta intentos ilimitados: un atacante puede
probar contraseñas al ritmo que le permita la red.  bcrypt encarece cada intento,
pero no lo impide.

Diseño
------
El contador va **por IP**, no por usuario.  Es deliberado: limitar por nombre de
usuario permitiría a cualquiera bloquear la cuenta de otro simplemente fallando
adivinanzas contra ella (denegación de servicio sobre el usuario legítimo).  La
IP es la que paga el coste de sus propios intentos.

Se usa una ventana deslizante en memoria.  Finlytics es self-hosted y de un solo
usuario, así que no hace falta almacenamiento compartido; si algún día corre con
varios workers, este módulo es el punto donde cambiar a Redis.

Un login correcto limpia el contador de esa IP, de modo que equivocarse un par de
veces y acertar después no deja rastro.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

__all__ = ["RateLimiter", "RateLimitResult", "client_ip"]


@dataclass(frozen=True)
class RateLimitResult:
    """Resultado de consultar el limitador."""

    allowed: bool
    """False cuando la petición debe rechazarse con 429."""

    retry_after: int
    """Segundos que faltan para que vuelva a haber cupo. 0 si está permitido."""

    remaining: int
    """Intentos que quedan en la ventana actual."""


@dataclass
class RateLimiter:
    """Ventana deslizante en memoria, segura entre hilos.

    Parameters
    ----------
    max_attempts:
        Intentos permitidos dentro de la ventana.
    window_seconds:
        Amplitud de la ventana.
    """

    max_attempts: int
    window_seconds: int
    _hits: dict[str, deque[float]] = field(default_factory=dict, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def check(self, key: str, *, now: float | None = None) -> RateLimitResult:
        """Registra un intento para ``key`` y dice si se admite.

        Cuenta el intento SOLO si se admite: una vez bloqueada, la IP no alarga
        su propio castigo golpeando el endpoint, que es lo que ocurriría si cada
        petición rechazada empujara también la ventana.
        """
        moment = time.monotonic() if now is None else now

        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits

            cutoff = moment - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.max_attempts:
                retry_after = max(1, int(hits[0] + self.window_seconds - moment) + 1)
                return RateLimitResult(allowed=False, retry_after=retry_after, remaining=0)

            hits.append(moment)
            return RateLimitResult(
                allowed=True,
                retry_after=0,
                remaining=self.max_attempts - len(hits),
            )

    def reset(self, key: str) -> None:
        """Olvida los intentos de ``key`` (se llama tras autenticarse bien)."""
        with self._lock:
            self._hits.pop(key, None)

    def purge(self, *, now: float | None = None) -> int:
        """Descarta las claves cuya ventana ha expirado por completo.

        Evita que el diccionario crezca sin límite cuando muchas IP distintas
        hacen algún intento suelto.  Devuelve cuántas claves se eliminaron.
        """
        moment = time.monotonic() if now is None else now
        cutoff = moment - self.window_seconds

        with self._lock:
            stale = [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
            for k in stale:
                del self._hits[k]
            return len(stale)

    def clear(self) -> None:
        """Vacía todo el estado. Pensado para aislar tests entre sí."""
        with self._lock:
            self._hits.clear()


def client_ip(request) -> str:  # noqa: ANN001 — evita importar Starlette aquí
    """IP del cliente tal y como la ve la aplicación.

    Se lee de la conexión, NO de ``X-Forwarded-For``: ese encabezado lo puede
    poner cualquiera, así que confiar en él dejaría el límite en nada (bastaría
    con variar el valor en cada intento).  Tras un proxy inverso hay que
    configurar el propio proxy —o uvicorn con ``--proxy-headers``— para que la
    IP real llegue ya resuelta en la conexión.
    """
    client = getattr(request, "client", None)
    if client is None or not getattr(client, "host", None):
        return "unknown"
    return str(client.host)
