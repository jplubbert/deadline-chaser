"""Capa estadística base: clasifica trabajos por holgura vs lead_time + σ.

Todo en horas hábiles. El nivel_roce NO afecta esta clasificación; queda
disponible en el dict de salida para que la capa de redacción ajuste tono.

Los umbrales corresponden a percentiles de la distribución normal del
lead_time esperado por persona (μ = lead_time_promedio_horas, σ):
    p97 = μ + 2σ  (≈ percentil 97.5)
    p84 = μ +  σ  (≈ percentil 84.1)
    p50 = μ        (≈ percentil 50)
La zona "critico" se gatilla cuando la holgura cae bajo p50: ya no es
estadísticamente probable que la persona alcance a entregar.
"""

from decimal import Decimal
from typing import Literal

from psycopg.rows import dict_row

from core.db import get_connection
from core.queries import calcular_holgura_horas_habiles

NivelRoce = Literal["bajo", "medio", "alto"]
Zona = Literal["p97", "p84", "p50", "critico"]

SIGMA_DEFAULT_FRACCION = Decimal("1.00")
_Q = Decimal("0.01")


def calcular_umbrales(
    lead_time_horas: Decimal,
    sigma_horas: Decimal,
) -> dict[str, Decimal]:
    """Devuelve los 3 umbrales (p97, p84, p50) en horas hábiles."""
    lead = Decimal(lead_time_horas)
    sig = Decimal(sigma_horas)
    return {
        "p97": (lead + Decimal(2) * sig).quantize(_Q),
        "p84": (lead + sig).quantize(_Q),
        "p50": lead.quantize(_Q),
    }


def clasificar_zona(
    horas_deadline: Decimal,
    p97: Decimal,
    p84: Decimal,
    p50: Decimal,
) -> Zona:
    if horas_deadline >= p97:
        return "p97"
    if horas_deadline >= p84:
        return "p84"
    if horas_deadline >= p50:
        return "p50"
    return "critico"


def evaluar_trabajo(trabajo_id: int) -> dict | None:
    sql = """
        SELECT  t.trabajo_id,
                t.descripcion,
                t.deadline,
                p.persona_id,
                p.nombre        AS persona_nombre,
                p.correo        AS persona_correo,
                p.nivel_roce,
                p.lead_time_promedio_horas,
                r.nombre        AS rol,
                a.nombre        AS area
        FROM    trabajos t
        LEFT JOIN personas p ON p.persona_id = t.persona_asignada_id
        LEFT JOIN roles    r ON r.rol_id     = p.rol_id
        LEFT JOIN areas    a ON a.area_id    = p.area_id
        WHERE   t.trabajo_id = %s
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (trabajo_id,))
        row = cur.fetchone()

    if row is None or row["persona_id"] is None:
        return None
    lead = row["lead_time_promedio_horas"]
    if lead is None:
        return None

    lead_h = Decimal(lead).quantize(_Q)
    # σ no existe como columna todavía; default = lead * 0.3.
    # Cuando se persista σ por persona, leerla acá y caer al default solo si es None.
    sigma_h = (lead_h * SIGMA_DEFAULT_FRACCION).quantize(_Q)

    umbrales = calcular_umbrales(lead_h, sigma_h)
    horas_deadline = calcular_holgura_horas_habiles(trabajo_id)
    zona = clasificar_zona(
        horas_deadline,
        umbrales["p97"],
        umbrales["p84"],
        umbrales["p50"],
    )

    return {
        "trabajo_id": row["trabajo_id"],
        "descripcion": row["descripcion"],
        "deadline": row["deadline"],
        "persona_id": row["persona_id"],
        "persona": row["persona_nombre"],
        "rol": row["rol"],
        "area": row["area"],
        "nivel_roce": row["nivel_roce"],
        "correo": row["persona_correo"],
        "horas_deadline": horas_deadline,
        "lead_time_horas": lead_h,
        "sigma_horas": sigma_h,
        **umbrales,
        "zona": zona,
    }
