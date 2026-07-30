"""Tests del limitador de intentos de autenticación.

Cubren la mecánica de la ventana deslizante por separado del endpoint, para que
un fallo señale directamente si el problema está en el algoritmo o en cómo lo usa
la API.
"""

from __future__ import annotations

from finlytics.auth.ratelimit import RateLimiter, client_ip


class _FakeClient:
    def __init__(self, host: str | None) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str | None = "203.0.113.7", *, no_client: bool = False) -> None:
        self.client = None if no_client else _FakeClient(host)


# ── Ventana deslizante ────────────────────────────────────────────────────────

def test_allows_up_to_the_limit():
    limiter = RateLimiter(max_attempts=3, window_seconds=60)

    results = [limiter.check("ip", now=0.0) for _ in range(3)]

    assert [r.allowed for r in results] == [True, True, True]
    assert [r.remaining for r in results] == [2, 1, 0]


def test_blocks_once_the_limit_is_exceeded():
    limiter = RateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        limiter.check("ip", now=0.0)

    verdict = limiter.check("ip", now=0.0)

    assert verdict.allowed is False
    assert verdict.remaining == 0
    assert verdict.retry_after > 0


def test_blocked_attempts_do_not_extend_the_penalty():
    """Golpear el endpoint estando bloqueado no debe alargar el castigo.

    Si cada intento rechazado empujara también la ventana, una IP bloqueada se
    mantendría bloqueada indefinidamente sólo por seguir reintentando.
    """
    limiter = RateLimiter(max_attempts=2, window_seconds=60)
    limiter.check("ip", now=0.0)
    limiter.check("ip", now=0.0)

    # Rechazado repetidamente durante la ventana...
    for t in (10.0, 20.0, 30.0, 50.0):
        assert limiter.check("ip", now=t).allowed is False

    # ...y aun así vuelve a haber cupo cuando expira el primer intento.
    assert limiter.check("ip", now=61.0).allowed is True


def test_window_slides():
    limiter = RateLimiter(max_attempts=2, window_seconds=60)
    limiter.check("ip", now=0.0)
    limiter.check("ip", now=30.0)

    assert limiter.check("ip", now=45.0).allowed is False
    # En t=61 ha expirado el intento de t=0, así que queda un hueco.
    assert limiter.check("ip", now=61.0).allowed is True
    # Pero el de t=30 sigue vivo, así que no hay un segundo hueco.
    assert limiter.check("ip", now=61.0).allowed is False


def test_keys_are_independent():
    limiter = RateLimiter(max_attempts=1, window_seconds=60)

    assert limiter.check("ip-a", now=0.0).allowed is True
    assert limiter.check("ip-a", now=0.0).allowed is False
    # Otra IP no hereda el bloqueo de la primera.
    assert limiter.check("ip-b", now=0.0).allowed is True


def test_reset_clears_a_single_key():
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    limiter.check("ip-a", now=0.0)
    limiter.check("ip-b", now=0.0)

    limiter.reset("ip-a")

    assert limiter.check("ip-a", now=0.0).allowed is True
    assert limiter.check("ip-b", now=0.0).allowed is False


def test_retry_after_is_at_least_one_second():
    """Nunca debe anunciarse un Retry-After de 0: sugeriría reintentar ya."""
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    limiter.check("ip", now=0.0)

    # Justo al final de la ventana, donde el redondeo podría dar 0.
    verdict = limiter.check("ip", now=59.99)

    assert verdict.allowed is False
    assert verdict.retry_after >= 1


# ── Limpieza de memoria ───────────────────────────────────────────────────────

def test_purge_drops_expired_keys_only():
    limiter = RateLimiter(max_attempts=5, window_seconds=60)
    limiter.check("vieja", now=0.0)
    limiter.check("reciente", now=100.0)

    removed = limiter.purge(now=120.0)

    assert removed == 1
    # La reciente conserva su historial.
    assert limiter.check("reciente", now=120.0).remaining == 3


def test_clear_wipes_everything():
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    limiter.check("ip-a", now=0.0)
    limiter.check("ip-b", now=0.0)

    limiter.clear()

    assert limiter.check("ip-a", now=0.0).allowed is True
    assert limiter.check("ip-b", now=0.0).allowed is True


# ── Extracción de la IP ───────────────────────────────────────────────────────

def test_client_ip_reads_the_connection():
    assert client_ip(_FakeRequest("198.51.100.4")) == "198.51.100.4"


def test_client_ip_falls_back_when_absent():
    assert client_ip(_FakeRequest(no_client=True)) == "unknown"
    assert client_ip(_FakeRequest(host=None)) == "unknown"


def test_client_ip_ignores_forwarded_headers():
    """X-Forwarded-For es falsificable: confiar en él anularía el límite.

    Bastaría con enviar un valor distinto en cada intento para tener intentos
    ilimitados, así que la IP se toma siempre de la conexión.
    """
    request = _FakeRequest("198.51.100.4")
    request.headers = {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"}

    assert client_ip(request) == "198.51.100.4"
