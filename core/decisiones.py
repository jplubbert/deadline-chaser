"""Decide si corresponde enviar un correo nuevo o esperar.

`decidir_accion` es una función pura: recibe el snapshot del trabajo
evaluado, el último mensaje enviado (o None) y la hora actual, y devuelve
{accion, razon}. No hace I/O ni decide formato; eso es del orquestador.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from core.queries import _business_seconds_between

ORDEN_ZONA: dict[str, int] = {"p97": 0, "p84": 1, "p50": 2, "critico": 3}

FREQ_MIN_HORAS_HABILES: dict[str, Decimal] = {
    "p97": Decimal("40.00"),
    "p84": Decimal("24.00"),
    "p50": Decimal("8.00"),
    "critico": Decimal("4.00"),
}


def _horas_habiles_desde(enviado_at: datetime, ahora: datetime) -> Decimal:
    seconds = _business_seconds_between(enviado_at, ahora)
    return (Decimal(seconds) / Decimal(3600)).quantize(Decimal("0.01"))


def decidir_accion(
    trabajo_evaluado: dict[str, Any],
    ultimo_mensaje_enviado: dict[str, Any] | None,
    ahora: datetime,
) -> dict[str, str]:
    zona_actual = trabajo_evaluado["zona"]

    if ultimo_mensaje_enviado is None:
        return {
            "accion": "enviar",
            "razon": f"Primer contacto (zona {zona_actual}).",
        }

    zona_anterior = ultimo_mensaje_enviado.get("zona_al_enviar")
    if zona_anterior in ORDEN_ZONA and ORDEN_ZONA[zona_actual] > ORDEN_ZONA[zona_anterior]:
        return {
            "accion": "enviar",
            "razon": f"Zona empeoró: {zona_anterior} → {zona_actual}.",
        }

    horas_pasadas = _horas_habiles_desde(
        ultimo_mensaje_enviado["enviado_at"], ahora
    )
    freq_min = FREQ_MIN_HORAS_HABILES[zona_actual]

    if horas_pasadas >= freq_min:
        return {
            "accion": "enviar",
            "razon": (
                f"Zona {zona_actual}: pasaron {horas_pasadas}h hábiles desde el "
                f"último envío (mín. {freq_min}h)."
            ),
        }

    return {
        "accion": "esperar",
        "razon": (
            f"Zona {zona_actual}: solo {horas_pasadas}h hábiles desde el último "
            f"envío (mín. {freq_min}h)."
        ),
    }
