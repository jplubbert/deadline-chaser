"""Job diario: para cada trabajo pendiente decide si enviar o esperar."""

import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agente import generar_correo
from core.decisiones import decidir_accion
from core.enviar import enviar_mensaje
from core.mensajes import guardar_mensaje
from core.queries import (
    get_trabajos_pendientes,
    ultimo_mensaje_enviado_de_trabajo,
)
from core.zonas import evaluar_trabajo


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
        mensaje_dict = generar_correo(ev)
        mensaje_id = guardar_mensaje(mensaje_dict)
        mensaje_dict["mensaje_id"] = mensaje_id
        result = enviar_mensaje(mensaje_dict)

        enviados.append(
            {
                "trabajo_id": t["trabajo_id"],
                "zona": ev["zona"],
                "mensaje_id": mensaje_id,
                "gmail_id": result["gmail_message_id"],
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
            print(
                f"  trabajo {e['trabajo_id']}  zona={e['zona']}  "
                f"mensaje_id={e['mensaje_id']}  gmail_id={e['gmail_id']}"
            )
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
