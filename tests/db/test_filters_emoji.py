"""Reparto del emoji inicial en los nombres de etiqueta.

El patron usa cuantificadores posesivos para no dar pie al ReDoS polinomico que
senalaba CodeQL. Estos tests fijan las dos cosas que eso implica: que el reparto
normal no cambia, y que el caso degenerado (nombre formado solo por emojis) se
devuelve intacto en lugar de partirse.
"""

from __future__ import annotations

import time

import pytest

from finlytics.db.queries._filters import _split_leading_emoji

# ── Reparto habitual ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("raw", "esperado"),
    [
        ("\U0001F4A1 luz", ("\U0001F4A1", "luz")),
        ("\U0001F4A1luz", ("\U0001F4A1", "luz")),
        ("\U0001F4A1\t\tluz", ("\U0001F4A1", "luz")),
        ("\U0001F4A1   luz  ", ("\U0001F4A1", "luz")),
        ("\U0001F4A1\U0001F4A7 suministros", ("\U0001F4A1\U0001F4A7", "suministros")),
        ("\U0001F4A1 luz y gas", ("\U0001F4A1", "luz y gas")),
    ],
)
def test_separa_el_emoji_inicial(raw: str, esperado: tuple[str, str]):
    assert _split_leading_emoji(raw) == esperado


# ── Casos en los que el nombre se devuelve intacto ────────────────────────────

@pytest.mark.parametrize(
    "raw",
    [
        "luz",                                  # sin emoji
        "",                                     # vacio
        "   ",                                  # solo espacios
        "\U0001F4A1",                           # un solo emoji
        "\U0001F4A1 ",                          # emoji y espacio
        "\U0001F4A1\U0001F4A7",                 # solo emojis, sin espacio final
        "\U0001F4A1\U0001F4A7 ",                # solo emojis, con espacio final
        "\U0001F4A1 \t\n",                      # emoji y espacios variados
    ],
)
def test_devuelve_el_nombre_intacto(raw: str):
    """Si quitar el prefijo dejaria el nombre vacio, no se toca nada.

    Los dos casos de «solo emojis» son los que cambiaron al hacer posesivo el
    patron: antes «💡💧» se partia en emoji «💡» + nombre «💧», pero «💡💧 » (con
    espacio) no, porque el reparto dependia del backtracking. Ahora los dos se
    comportan igual y respetan el contrato de la funcion.
    """
    assert _split_leading_emoji(raw) == (None, raw)


# ── Ausencia de coste no lineal ───────────────────────────────────────────────

def test_el_coste_no_se_dispara_con_la_longitud():
    """El tiempo crece de forma lineal, no cuadratica, con la entrada.

    Se compara el peor caso conocido (emoji + muchos espacios y nada detras, que
    es lo que obligaba al motor a probar divisiones) a dos tamanos que se
    diferencian en 8x. Con coste cuadratico la relacion rondaria 64x.

    Aviso para quien lo lea luego: este test NO falla si se revierte el patron al
    permisivo de antes. Se comprobo. Aquel patron era ambiguo sobre el papel,
    pero CPython lo resolvia en tiempo lineal, asi que no habia nada explotable
    que medir. Esto es una red contra una regresion futura peor, no la prueba de
    que se arreglara una lentitud real.
    """
    def mide(n: int) -> float:
        entrada = "\U0001F525" + " \t" * n
        inicio = time.perf_counter()
        for _ in range(200):
            _split_leading_emoji(entrada)
        return time.perf_counter() - inicio

    mide(100)  # calentamiento, para no medir el coste de importar
    corto = mide(500)
    largo = mide(4000)

    # Margen amplio a proposito: la senal que interesa es «no es cuadratico»,
    # no un umbral fino que parpadee segun la maquina donde corra el CI.
    assert largo < corto * 24, f"crecimiento sospechoso: {corto=:.4f}s {largo=:.4f}s"
