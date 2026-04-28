"""Validación de respuestas: glosa LSC + detección de pelota."""

import re
from typing import Any

# IOC (6 dígitos) + RUT (8 dígitos + espacio + DV) + ID (6 dígitos) + 3 letras Resp.
GLOSA_RE = re.compile(
    r"IOC[\s:.\-]*(?P<ioc>\d{6})"
    r"[\s,;\-]+"
    r"RUT[\s:.\-]*(?P<rut>[\dKk \-]+?)"
    r"[\s,;\-]+"
    r"ID[\s:.\-]*(?P<id>\d{6})"
    r"[\s,;\-]+"
    r"(?:Resp[\s:.\-]+)?(?P<resp>[A-Za-zñÑ]{3})\b",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)

PATRONES_PELOTA = (
    "esto lo lleva",
    "lo lleva",
    "lo tiene",
    "deriva a",
    "derivo a",
    "consulta a",
    "consulta con",
    "le pregunté a",
    "le pregunte a",
    "se encarga",
    "lo ve",
)

_MULT_DV = (2, 3, 4, 5, 6, 7)


def _calcular_dv(numero: int) -> str:
    suma = 0
    i = 0
    n = numero
    while n > 0:
        suma += (n % 10) * _MULT_DV[i % len(_MULT_DV)]
        n //= 10
        i += 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def validar_rut(rut_str: str | None) -> dict[str, Any]:
    """Valida formato y DV. 10 chars = 8 dígitos + espacio + DV (0-9 o K mayúscula)."""
    errores: list[str] = []
    if rut_str is None or not rut_str:
        return {"valido": False, "errores": ["RUT vacío"]}

    if len(rut_str) != 10:
        errores.append(f"RUT debe tener 10 caracteres (tiene {len(rut_str)})")

    # Aún si la longitud está mal, intentamos validar lo que se puede.
    if len(rut_str) >= 9:
        base = rut_str[:8]
        sep = rut_str[8]
        if not base.isdigit():
            errores.append("Los primeros 8 caracteres deben ser dígitos")
        if sep != " ":
            errores.append("Falta espacio antes del DV (posición 9)")
        if len(rut_str) >= 10:
            dv = rut_str[9]
            if dv == "k":
                errores.append("DV con 'k' minúscula (debe ser 'K' mayúscula)")
            elif not (dv.isdigit() or dv == "K"):
                errores.append(f"DV inválido: '{dv}' (debe ser 0-9 o K)")
            elif base.isdigit():
                esperado = _calcular_dv(int(base))
                if dv != esperado:
                    errores.append(
                        f"DV incorrecto (esperado '{esperado}', recibido '{dv}')"
                    )

    return {"valido": not errores, "errores": errores}


def validar_glosa(contenido: str) -> dict[str, Any]:
    """Parsea texto libre buscando línea con formato glosa LSC."""
    if not contenido:
        return {
            "tiene_glosa": False,
            "ioc": None, "rut_data": None, "id": None, "responsable": None,
            "errores": ["No se detectó formato de glosa válido"],
        }

    m = GLOSA_RE.search(contenido)
    if m is None:
        return {
            "tiene_glosa": False,
            "ioc": None, "rut_data": None, "id": None, "responsable": None,
            "errores": ["No se detectó formato de glosa válido"],
        }

    ioc = m.group("ioc")
    rut = m.group("rut").strip()
    id_glosa = m.group("id")
    resp = m.group("resp").upper()

    errores: list[str] = []
    val_rut = validar_rut(rut)
    if not val_rut["valido"]:
        errores.extend(f"RUT: {e}" for e in val_rut["errores"])

    return {
        "tiene_glosa": True,
        "ioc": ioc,
        "rut_data": rut,
        "id": id_glosa,
        "responsable": resp,
        "errores": errores,
    }


def detectar_pelota(contenido: str) -> dict[str, Any]:
    """Detecta si la persona derivó la responsabilidad a otra.

    Recorre todos los patrones; el primero que arroje un nombre con
    mayúscula gana. Si encuentra patrón(es) pero ningún nombre
    extraíble, devuelve hay_pelota=True con persona_mencionada=None.
    """
    if not contenido:
        return {"hay_pelota": False, "persona_mencionada": None}

    contenido_lower = contenido.lower()
    nombre_re = re.compile(
        r"\s+([A-ZÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ.]*(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñÁÉÍÓÚÑ.]*)?)"
    )

    encontrado_algun_patron = False
    for patron in PATRONES_PELOTA:
        idx = contenido_lower.find(patron)
        if idx == -1:
            continue
        encontrado_algun_patron = True
        after = contenido[idx + len(patron):]
        m = nombre_re.match(after)
        if m:
            return {
                "hay_pelota": True,
                "persona_mencionada": m.group(1).strip("."),
            }

    return {
        "hay_pelota": encontrado_algun_patron,
        "persona_mencionada": None,
    }
