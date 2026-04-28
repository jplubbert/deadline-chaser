"""Procesa las respuestas pendientes (validar glosa / detectar pelota) y
actualiza el estado de los trabajos correspondientes.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.lectura_respuestas import (
    obtener_respuestas_pendientes_de_procesar,
    procesar_respuesta,
)


def main() -> None:
    pendientes = obtener_respuestas_pendientes_de_procesar()
    print(f"Respuestas pendientes de procesar: {len(pendientes)}\n")

    contadores: dict[str, int] = {
        "respondido_ok": 0,
        "respuesta_con_errores": 0,
        "derivado": 0,
        "respuesta_ambigua": 0,
    }

    for r in pendientes:
        result = procesar_respuesta(r)
        contadores[result["tipo_resultado"]] = contadores.get(
            result["tipo_resultado"], 0
        ) + 1

        print("=" * 78)
        print(
            f"  mensaje_id={r['mensaje_id']}  trabajo_id={r['trabajo_id']}  "
            f"remitente_id={r['remitente_id']}"
        )
        print(f"  tipo_resultado: {result['tipo_resultado']}")
        print(f"  acción requerida: {result['accion_requerida']}")
        print(f"  detalle: {result['detalle']}")
        if result["tipo_resultado"] == "respuesta_con_errores":
            print("  validación de glosa:")
            for e in result["glosa"]["errores"]:
                print(f"    - {e}")
        elif result["tipo_resultado"] == "derivado":
            persona = result["pelota"]["persona_mencionada"] or "(sin identificar)"
            print(f"  persona mencionada: {persona}")
        elif result["tipo_resultado"] == "respondido_ok":
            print(f"  glosa: IOC={result['glosa']['ioc']}  "
                  f"RUT={result['glosa']['rut_data']}  "
                  f"ID={result['glosa']['id']}  Resp={result['glosa']['responsable']}")
        print()

    print("=" * 78)
    print("RESUMEN:")
    for tipo, n in contadores.items():
        print(f"  {tipo}: {n}")


if __name__ == "__main__":
    main()
