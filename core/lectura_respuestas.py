"""Lectura y procesamiento de respuestas a correos del agente."""

from typing import Any

from psycopg.rows import dict_row

from core.db import get_connection
from core.validador import detectar_pelota, validar_glosa

AGENTE_ID = 0


def obtener_respuestas_pendientes_de_procesar() -> list[dict[str, Any]]:
    """Respuestas (remitente_id != 0) aún no procesadas."""
    sql = """
        SELECT  m.mensaje_id, m.trabajo_id, m.remitente_id,
                m.contenido, m.asunto, m.gmail_message_id, m.timestamp
        FROM    mensajes m
        WHERE   m.remitente_id <> %s
                AND m.procesada = false
        ORDER BY m.timestamp ASC
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (AGENTE_ID,))
        return list(cur.fetchall())


def _marcar_procesada(mensaje_id: int) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE mensajes SET procesada = true WHERE mensaje_id = %s",
            (mensaje_id,),
        )


def _actualizar_estado_trabajo(trabajo_id: int, estado: str) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE trabajos SET estado = %s WHERE trabajo_id = %s",
            (estado, trabajo_id),
        )


def procesar_respuesta(respuesta: dict[str, Any]) -> dict[str, Any]:
    """Clasifica la respuesta, actualiza estado del trabajo, marca procesada."""
    contenido = respuesta.get("contenido") or ""
    glosa = validar_glosa(contenido)
    pelota = detectar_pelota(contenido)

    if glosa["tiene_glosa"] and not glosa["errores"]:
        tipo = "respondido_ok"
        accion = "ninguna"
        detalle = (
            f"Glosa válida: IOC={glosa['ioc']} RUT={glosa['rut_data']} "
            f"ID={glosa['id']} Resp={glosa['responsable']}"
        )
        estado = "respondido_ok"
    elif glosa["tiene_glosa"]:
        tipo = "respuesta_con_errores"
        accion = "enviar_aclaracion"
        detalle = "Glosa con errores: " + "; ".join(glosa["errores"])
        estado = "respuesta_con_errores"
    elif pelota["hay_pelota"]:
        tipo = "derivado"
        accion = "seguir_persiguiendo_persona_original"
        persona = pelota["persona_mencionada"] or "(sin identificar)"
        detalle = f"Pelota: derivó a {persona}"
        estado = "derivado"
    else:
        tipo = "respuesta_ambigua"
        accion = "clarificar"
        detalle = "Respuesta sin glosa válida ni derivación detectable"
        estado = "respuesta_ambigua"

    _actualizar_estado_trabajo(respuesta["trabajo_id"], estado)
    _marcar_procesada(respuesta["mensaje_id"])

    return {
        "mensaje_id": respuesta["mensaje_id"],
        "trabajo_id": respuesta["trabajo_id"],
        "tipo_resultado": tipo,
        "accion_requerida": accion,
        "detalle": detalle,
        "glosa": glosa,
        "pelota": pelota,
    }
