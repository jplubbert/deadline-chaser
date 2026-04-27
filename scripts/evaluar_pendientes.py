"""Evalúa todos los trabajos pendientes y los clasifica en zonas."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.queries import get_trabajos_pendientes
from core.zonas import evaluar_trabajo

ZONA_TAG = {"verde": "VERDE", "amarilla": "AMARILLA", "roja": "ROJA"}


def main() -> None:
    pendientes = get_trabajos_pendientes()
    print(f"Trabajos pendientes: {len(pendientes)}\n")

    header = (
        f"{'ID':>3}  {'PERSONA':<14} {'ROCE':<6} "
        f"{'HOLGURA':>9} {'UMBRAL':>9}  {'ZONA':<9}  DESCRIPCION"
    )
    print(header)
    print("-" * len(header))

    for t in pendientes:
        ev = evaluar_trabajo(t["trabajo_id"])
        if ev is None:
            print(
                f"{t['trabajo_id']:>3}  "
                f"{(t['asignado_nombre'] or '-')[:14]:<14} "
                f"{'-':<6} "
                f"{'-':>9} {'-':>9}  {'sin_datos':<9}  "
                f"{(t['descripcion'] or '')[:35]}"
            )
            continue

        print(
            f"{ev['trabajo_id']:>3}  "
            f"{(ev['persona'] or '-')[:14]:<14} "
            f"{ev['nivel_roce']:<6} "
            f"{str(ev['holgura']):>9} "
            f"{str(ev['umbral_verde']):>9}  "
            f"{ZONA_TAG[ev['zona']]:<9}  "
            f"{(ev['descripcion'] or '')[:35]}"
        )


if __name__ == "__main__":
    main()
