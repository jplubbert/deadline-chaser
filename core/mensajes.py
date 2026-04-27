"""Persistencia de mensajes generados por el agente."""

from typing import Any

from core.db import get_connection


def guardar_mensaje(mensaje: dict[str, Any]) -> int:
    """Inserta el mensaje en la tabla `mensajes` y devuelve el mensaje_id."""
    sql = """
        INSERT INTO mensajes (
            trabajo_id, remitente_id, destinatarios_to, destinatarios_cc,
            asunto, contenido
        ) VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING mensaje_id
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            sql,
            (
                mensaje["trabajo_id"],
                mensaje["remitente_id"],
                mensaje["destinatarios_to"],
                mensaje["destinatarios_cc"],
                mensaje["asunto"],
                mensaje["contenido"],
            ),
        )
        return cur.fetchone()[0]
