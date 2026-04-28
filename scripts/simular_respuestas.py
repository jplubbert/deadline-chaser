"""Simula respuestas a los últimos correos enviados por el agente."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.simulador import (
    PERFILES_PERSONA,
    simular_respuesta,
    simular_respuestas_a_todos_pendientes,
)


def main() -> None:
    resultados = simular_respuestas_a_todos_pendientes()

    n_respondio = sum(1 for r in resultados if r["estado"] == "respondio")
    n_no = sum(1 for r in resultados if r["estado"] == "no_respondio")
    n_skip = sum(
        1 for r in resultados
        if r["estado"] in ("respuesta_ya_existente", "sin_perfil_simulable")
    )

    print(f"Hilos pendientes evaluados: {len(resultados)}")
    print(f"  → respondieron:  {n_respondio}")
    print(f"  → no respondió:  {n_no}")
    print(f"  → omitidos:      {n_skip}\n")

    for r in resultados:
        perfil = PERFILES_PERSONA.get(r["respondio_id"]) if r["respondio_id"] else None
        nombre = perfil["nombre"] if perfil else "—"
        print("=" * 78)
        print(
            f"  trabajo {r['trabajo_id']}  estado={r['estado']}  "
            f"tipo={r['tipo']}  por={nombre}"
        )
        if r.get("mensaje_simulado_id"):
            print(f"  mensaje_simulado_id={r['mensaje_simulado_id']}")
        if r.get("contenido"):
            print()
            print(r["contenido"])
        print()

    # ----- ejemplo dirigido: Yolanda con error de RUT -----
    print("=" * 78)
    print("  EJEMPLO DIRIGIDO: Yolanda P. (id=1, caotico) → caso 'mal' con RUT roto")
    print("=" * 78)
    for _ in range(50):
        sim = simular_respuesta(1, "(correo de seguimiento del agente)", "demo-id")
        if sim["tipo"] == "caotico_mal":
            print(sim["contenido"])
            break
    else:
        print("(en 50 intentos no salió la rama 'mal' — improbable)")


if __name__ == "__main__":
    main()
