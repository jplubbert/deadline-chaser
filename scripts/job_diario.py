"""Job diario: para cada trabajo pendiente decide si enviar o esperar."""

import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agente import generar_correo
from core.db import get_connection
from core.decisiones import decidir_accion
from core.enviar import enviar_mensaje
from core.mensajes import guardar_mensaje
from core.queries import (
    get_trabajos_pendientes,
    ultima_respuesta_a_trabajo,
    ultimo_mensaje_enviado_de_trabajo,
)
from core.validador import detectar_pelota, validar_glosa
from core.zonas import evaluar_trabajo


def _resetear_estado_trabajo(trabajo_id: int) -> None:
    """Tras enviar aclaracion/derivado, vuelve el estado a 'pendiente'."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE trabajos SET estado = 'pendiente' WHERE trabajo_id = %s",
            (trabajo_id,),
        )


def _construir_contexto_extra(tipo_correo: str, trabajo_id: int) -> dict | None:
    if tipo_correo not in ("aclaracion_errores", "derivado_volver_a_la_misma"):
        return None
    respuesta = ultima_respuesta_a_trabajo(trabajo_id)
    if respuesta is None:
        return None
    if tipo_correo == "aclaracion_errores":
        glosa = validar_glosa(respuesta["contenido"] or "")
        return {
            "respuesta_anterior": respuesta["contenido"],
            "errores_detectados": glosa["errores"] or [
                "No se detectó formato de glosa válido"
            ],
        }
    # derivado_volver_a_la_misma
    pelota = detectar_pelota(respuesta["contenido"] or "")
    return {
        "persona_a_la_que_derivo": pelota.get("persona_mencionada") or "otra persona",
    }


def main() -> None:
    ahora = datetime.now()
    pendientes = get_trabajos_pendientes()

    enviados: list[dict] = []
    en_espera: list[dict] = []
    saltados: list[dict] = []

    for t in pendientes:
        ev = evaluar_trabajo(t["trabajo_id"])
        if ev is None:
            saltados.append(
                {"trabajo_id": t["trabajo_id"], "razon": "no se puede evaluar"}
            )
            continue

        ultimo = ultimo_mensaje_enviado_de_trabajo(t["trabajo_id"])
        decision = decidir_accion(ev, ultimo, ahora)

        if decision["accion"] == "esperar":
            en_espera.append(
                {
                    "trabajo_id": t["trabajo_id"],
                    "zona": ev["zona"],
                    "razon": decision["razon"],
                }
            )
            continue

        # accion == "enviar"
        tipo_correo = decision.get("tipo_correo") or "primer_envio"
        contexto_extra = _construir_contexto_extra(tipo_correo, t["trabajo_id"])
        mensaje_dict = generar_correo(
            ev, tipo_correo=tipo_correo, contexto_extra=contexto_extra
        )
        mensaje_id = guardar_mensaje(mensaje_dict)
        mensaje_dict["mensaje_id"] = mensaje_id
        result = enviar_mensaje(
            mensaje_dict,
            adjunto_bytes=mensaje_dict.get("adjunto_bytes"),
            nombre_adjunto=mensaje_dict.get("nombre_adjunto"),
        )

        # Si la decisión vino de un estado-respuesta (aclaracion/derivado),
        # reseteamos a 'pendiente' para no re-disparar la misma acción mañana.
        if tipo_correo in ("aclaracion_errores", "derivado_volver_a_la_misma"):
            _resetear_estado_trabajo(t["trabajo_id"])

        enviados.append(
            {
                "trabajo_id": t["trabajo_id"],
                "zona": ev["zona"],
                "tipo_correo": tipo_correo,
                "mensaje_id": mensaje_id,
                "gmail_id": result["gmail_message_id"],
                "tiene_adjunto": result.get("tiene_adjunto", False),
                "nombre_adjunto": mensaje_dict.get("nombre_adjunto"),
                "razon": decision["razon"],
            }
        )

    # ---- resumen ----
    print(f"=== JOB DIARIO {ahora.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    print(f"Trabajos pendientes evaluados: {len(pendientes)}")
    print(f"  → enviados:  {len(enviados)}")
    print(f"  → en espera: {len(en_espera)}")
    if saltados:
        print(f"  → saltados:  {len(saltados)}")

    if enviados:
        print("\n--- ENVIADOS ---")
        for e in enviados:
            adj = (
                f"  adjunto: {e['nombre_adjunto']}"
                if e["tiene_adjunto"]
                else "  adjunto: —"
            )
            print(
                f"  trabajo {e['trabajo_id']}  zona={e['zona']}  "
                f"tipo={e['tipo_correo']}  mensaje_id={e['mensaje_id']}  "
                f"gmail_id={e['gmail_id']}"
            )
            print(adj)
            print(f"    razón: {e['razon']}")

    if en_espera:
        print("\n--- EN ESPERA ---")
        for e in en_espera:
            print(f"  trabajo {e['trabajo_id']}  zona={e['zona']}")
            print(f"    razón: {e['razon']}")

    if saltados:
        print("\n--- SALTADOS ---")
        for s in saltados:
            print(f"  trabajo {s['trabajo_id']}: {s['razon']}")


if __name__ == "__main__":
    main()
