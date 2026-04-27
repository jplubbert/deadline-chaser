"""Smoke test: ejercita las 3 funciones de core.queries y muestra resultados."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.queries import (
    calcular_holgura_horas_habiles,
    get_personas,
    get_trabajos_pendientes,
)


def _hr(title: str) -> None:
    line = "=" * 72
    print(f"\n{line}\n  {title}\n{line}")


def main() -> None:
    _hr("PERSONAS")
    personas = get_personas()
    print(f"Total: {len(personas)}\n")
    print(
        f"{'ID':>3}  {'NOMBRE':<14} {'ROL':<14} {'AREA':<22} "
        f"{'ROCE':<6} {'LEAD(h)':>8}"
    )
    print("-" * 72)
    for p in personas:
        print(
            f"{p['persona_id']:>3}  "
            f"{(p['nombre'] or '')[:14]:<14} "
            f"{(p['rol'] or '-')[:14]:<14} "
            f"{(p['area'] or '-')[:22]:<22} "
            f"{(p['nivel_roce'] or '-'):<6} "
            f"{str(p['lead_time_promedio_horas'] or '-'):>8}"
        )

    _hr("TRABAJOS PENDIENTES")
    trabajos = get_trabajos_pendientes()
    print(f"Total: {len(trabajos)}\n")
    print(
        f"{'ID':>3}  {'DEADLINE':<19} {'ASIGNADO':<14} "
        f"{'HOLGURA_DB':>11}  DESCRIPCION"
    )
    print("-" * 72)
    for t in trabajos:
        print(
            f"{t['trabajo_id']:>3}  "
            f"{t['deadline'].strftime('%Y-%m-%d %H:%M'):<19} "
            f"{(t['asignado_nombre'] or '-')[:14]:<14} "
            f"{str(t['holgura_horas'] or '-'):>11}  "
            f"{(t['descripcion'] or '')[:35]}"
        )

    _hr("HOLGURA EN HORAS HÁBILES (cálculo en vivo)")
    if not trabajos:
        print("No hay trabajos pendientes.")
        return
    for t in trabajos[:3]:
        holgura = calcular_holgura_horas_habiles(t["trabajo_id"])
        flag = "ATRASADO" if holgura is not None and holgura < 0 else "OK"
        print(
            f"trabajo_id={t['trabajo_id']:>2}  "
            f"deadline={t['deadline'].strftime('%Y-%m-%d %H:%M')}  "
            f"holgura_habiles={holgura} h  [{flag}]  "
            f"-> {t['descripcion'][:40]}"
        )


if __name__ == "__main__":
    main()
