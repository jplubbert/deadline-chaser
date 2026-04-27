from decimal import Decimal
from typing import Literal

from psycopg.rows import dict_row

from core.db import get_connection
from core.queries import calcular_holgura_horas_habiles

NivelRoce = Literal["bajo", "medio", "alto"]
Zona = Literal["verde", "amarilla", "roja"]

BUFFERS_POR_ROCE: dict[NivelRoce, Decimal] = {
    "bajo": Decimal("0.30"),
    "medio": Decimal("0.50"),
    "alto": Decimal("0.80"),
}

Z_95 = Decimal("1.645")
SIGMA_DEFAULT_FRACCION = Decimal("0.30")
_Q = Decimal("0.01")


def calcular_umbral_zona_verde(
    lead_time_promedio: Decimal,
    sigma: Decimal,
    nivel_roce: NivelRoce,
) -> Decimal:
    lead = Decimal(lead_time_promedio)
    sig = Decimal(sigma)
    umbral_95 = lead + Z_95 * sig
    factor = Decimal(1) + BUFFERS_POR_ROCE[nivel_roce]
    return (umbral_95 * factor).quantize(_Q)


def clasificar_zona(
    holgura_horas_habiles: Decimal,
    umbral_verde: Decimal,
) -> Zona:
    if holgura_horas_habiles >= umbral_verde:
        return "verde"
    if holgura_horas_habiles >= umbral_verde / Decimal(2):
        return "amarilla"
    return "roja"


def evaluar_trabajo(trabajo_id: int) -> dict | None:
    sql = """
        SELECT  t.trabajo_id,
                t.descripcion,
                t.deadline,
                p.persona_id,
                p.nombre        AS persona_nombre,
                p.nivel_roce,
                p.lead_time_promedio_horas
        FROM    trabajos t
        LEFT JOIN personas p ON p.persona_id = t.persona_asignada_id
        WHERE   t.trabajo_id = %s
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (trabajo_id,))
        row = cur.fetchone()

    if row is None or row["persona_id"] is None:
        return None
    lead = row["lead_time_promedio_horas"]
    if lead is None or row["nivel_roce"] is None:
        return None

    sigma = (Decimal(lead) * SIGMA_DEFAULT_FRACCION).quantize(_Q)
    umbral = calcular_umbral_zona_verde(lead, sigma, row["nivel_roce"])
    holgura = calcular_holgura_horas_habiles(trabajo_id)

    return {
        "trabajo_id": row["trabajo_id"],
        "descripcion": row["descripcion"],
        "persona": row["persona_nombre"],
        "nivel_roce": row["nivel_roce"],
        "holgura": holgura,
        "umbral_verde": umbral,
        "zona": clasificar_zona(holgura, umbral),
    }
