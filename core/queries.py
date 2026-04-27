from datetime import datetime, time, timedelta
from decimal import Decimal

from psycopg.rows import dict_row

from core.db import get_connection

WORKDAY_START = time(9, 0)
WORKDAY_END = time(17, 0)
WORKDAY_SECONDS = (
    WORKDAY_END.hour * 3600 + WORKDAY_END.minute * 60
) - (WORKDAY_START.hour * 3600 + WORKDAY_START.minute * 60)


def get_personas() -> list[dict]:
    sql = """
        SELECT  p.persona_id,
                p.nombre,
                p.correo,
                r.nombre AS rol,
                a.nombre AS area,
                p.nivel_roce,
                p.lead_time_promedio_horas
        FROM    personas p
        LEFT JOIN roles r ON r.rol_id  = p.rol_id
        LEFT JOIN areas a ON a.area_id = p.area_id
        ORDER BY p.persona_id
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return cur.fetchall()


def get_trabajos_pendientes() -> list[dict]:
    sql = """
        SELECT  t.trabajo_id,
                t.descripcion,
                t.deadline,
                t.estado,
                t.holgura_horas,
                p.persona_id   AS asignado_id,
                p.nombre       AS asignado_nombre,
                p.correo       AS asignado_correo
        FROM    trabajos t
        LEFT JOIN personas p ON p.persona_id = t.persona_asignada_id
        WHERE   t.estado = 'pendiente'
        ORDER BY t.deadline ASC
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return cur.fetchall()


def _business_seconds_between(start: datetime, end: datetime) -> int:
    """Segundos hábiles (lun–vie, 09:00–18:00) entre `start` y `end`.

    Si `end` está antes que `start` devuelve un negativo: el trabajo está
    atrasado. La cuenta incluye solo el tramo que cae dentro de la jornada.
    """
    if end == start:
        return 0
    sign = 1
    if end < start:
        start, end = end, start
        sign = -1

    total = 0
    cursor = start
    while cursor < end:
        if cursor.weekday() < 5:
            day_start = datetime.combine(cursor.date(), WORKDAY_START)
            day_end = datetime.combine(cursor.date(), WORKDAY_END)
            window_start = max(cursor, day_start)
            window_end = min(end, day_end)
            if window_end > window_start:
                total += int((window_end - window_start).total_seconds())
        next_day = (cursor + timedelta(days=1)).date()
        cursor = datetime.combine(next_day, time(0, 0))

    return sign * total


def ultimo_mensaje_enviado_de_trabajo(trabajo_id: int) -> dict | None:
    """Devuelve el mensaje más reciente con `enviado_at NOT NULL` para el trabajo.

    Devuelve `None` si no hay ningún mensaje enviado para ese trabajo.
    """
    sql = """
        SELECT  mensaje_id, trabajo_id, remitente_id,
                destinatarios_to, destinatarios_cc,
                asunto, contenido,
                gmail_message_id, timestamp, enviado_at,
                zona_al_enviar
        FROM    mensajes
        WHERE   trabajo_id = %s AND enviado_at IS NOT NULL
        ORDER BY enviado_at DESC
        LIMIT   1
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (trabajo_id,))
        return cur.fetchone()


def calcular_holgura_horas_habiles(
    trabajo_id: int,
    *,
    ahora: datetime | None = None,
) -> Decimal | None:
    """Holgura en horas hábiles entre `ahora` y el deadline del trabajo.

    Devuelve `None` si el trabajo no existe. Negativo significa atraso.
    """
    if ahora is None:
        ahora = datetime.now()

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT deadline FROM trabajos WHERE trabajo_id = %s",
            (trabajo_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        deadline: datetime = row[0]

    seconds = _business_seconds_between(ahora, deadline)
    return (Decimal(seconds) / Decimal(3600)).quantize(Decimal("0.01"))
