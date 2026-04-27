"""Evalúa todos los trabajos pendientes y los clasifica en zonas."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.queries import get_trabajos_pendientes
from core.zonas import evaluar_trabajo

ZONA_TAG = {
    "p97": "p97",
    "p84": "p84",
    "p50": "p50",
    "critico": "CRITICO",
}


def main() -> None:
    pendientes = get_trabajos_pendientes()
    print(f"Trabajos pendientes: {len(pendientes)}\n")

    header = (
        f"{'ID':>3}  {'PERSONA':<14} {'ROL':<10} {'ROCE':<6} "
        f"{'DDL(h)':>7} {'LEAD':>7} {'SIGMA':>7} "
        f"{'p50':>7} {'p84':>7} {'p97':>7}  "
        f"{'ZONA':<8}  DESC"
    )
    print(header)
    print("-" * len(header))

    for t in pendientes:
        ev = evaluar_trabajo(t["trabajo_id"])
        if ev is None:
            print(
                f"{t['trabajo_id']:>3}  "
                f"{(t['asignado_nombre'] or '-')[:14]:<14} "
                f"{'-':<10} {'-':<6} "
                f"{'-':>7} {'-':>7} {'-':>7} "
                f"{'-':>7} {'-':>7} {'-':>7}  "
                f"{'sin_datos':<8}  "
                f"{(t['descripcion'] or '')[:30]}"
            )
            continue

        print(
            f"{ev['trabajo_id']:>3}  "
            f"{(ev['persona'] or '-')[:14]:<14} "
            f"{(ev['rol'] or '-')[:10]:<10} "
            f"{ev['nivel_roce']:<6} "
            f"{str(ev['horas_deadline']):>7} "
            f"{str(ev['lead_time_horas']):>7} "
            f"{str(ev['sigma_horas']):>7} "
            f"{str(ev['p50']):>7} "
            f"{str(ev['p84']):>7} "
            f"{str(ev['p97']):>7}  "
            f"{ZONA_TAG[ev['zona']]:<8}  "
            f"{(ev['descripcion'] or '')[:30]}"
        )


if __name__ == "__main__":
    main()
