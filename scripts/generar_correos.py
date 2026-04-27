"""Genera, persiste y muestra los correos para los trabajos pendientes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agente import generar_correo
from core.db import get_connection
from core.mensajes import guardar_mensaje
from core.queries import get_trabajos_pendientes
from core.zonas import evaluar_trabajo

ZONA_LABEL = {
    "p97": "p97 (holgada)",
    "p84": "p84 (firme)",
    "p50": "p50 (urgente)",
    "critico": "CRITICO",
}


def _lookup_personas() -> dict[int, tuple[str, str]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT persona_id, nombre, correo FROM personas")
        return {pid: (nombre, correo) for pid, nombre, correo in cur.fetchall()}


def _fmt_destinatarios(ids: list[int], lookup: dict[int, tuple[str, str]]) -> str:
    if not ids:
        return "—"
    return ", ".join(f"{lookup[i][1]} (id={i})" for i in ids)


def main() -> None:
    pendientes = get_trabajos_pendientes()
    personas = _lookup_personas()
    print(f"Generando correos para {len(pendientes)} trabajos pendientes...\n")

    for t in pendientes:
        ev = evaluar_trabajo(t["trabajo_id"])
        if ev is None:
            print(
                f"[skip] trabajo_id={t['trabajo_id']} no se puede evaluar "
                f"(sin asignado o sin lead_time).\n"
            )
            continue

        mensaje = generar_correo(ev)
        mensaje_id = guardar_mensaje(mensaje)

        print("=" * 78)
        print(
            f"  Trabajo #{ev['trabajo_id']}  ·  Zona {ZONA_LABEL[ev['zona']]}  "
            f"·  mensaje_id={mensaje_id}"
        )
        print(
            f"  Persona asignada: {ev['persona']} "
            f"({ev['rol']}, {ev['area']}, roce {ev['nivel_roce']})"
        )
        print(
            f"  Holgura {ev['horas_deadline']} h  "
            f"(lead {ev['lead_time_horas']} h, p97 {ev['p97']} h)"
        )
        print("=" * 78)
        print(f"From:    {personas[mensaje['remitente_id']][1]} (id={mensaje['remitente_id']})")
        print(f"To:      {_fmt_destinatarios(mensaje['destinatarios_to'], personas)}")
        print(f"Cc:      {_fmt_destinatarios(mensaje['destinatarios_cc'], personas)}")
        print(f"Subject: {mensaje['asunto']}")
        print()
        print(mensaje["contenido"])
        print()


if __name__ == "__main__":
    main()
