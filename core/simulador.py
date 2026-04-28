"""Simulador de respuestas a correos del agente.

Permite testear el ciclo completo agente → persona → agente sin tráfico
real. Las respuestas se construyen con templates hardcodeados en español
chileno corporativo (sin LLM) y se persisten en la tabla `mensajes` con
gmail_message_id `sim_<uuid>`.
"""

from __future__ import annotations

import random
import string
import uuid
from datetime import datetime, timedelta
from typing import Any

from psycopg.rows import dict_row

from core.db import get_connection

AGENTE_ID = 0

# persona_id → arquetipo + efectividad informativa
PERFILES_PERSONA: dict[int, dict[str, Any]] = {
    1: {"nombre": "Yolanda P.",   "arquetipo": "caotico", "efectividad": 0.40},
    2: {"nombre": "Pedro M.",     "arquetipo": "certero", "efectividad": 0.99},
    3: {"nombre": "Patricia G.",  "arquetipo": "mixto",   "efectividad": 0.70},
    4: {"nombre": "Carlos R.",    "arquetipo": "caotico", "efectividad": 0.40},
    5: {"nombre": "Andrea S.",    "arquetipo": "certero", "efectividad": 0.99},
}

# Distribución del arquetipo "caotico"
_RAMAS_CAOTICO = ("mal", "pelota", "tarde", "ignora")
_PESOS_CAOTICO = (30, 20, 10, 40)


# ---------- RUT ------------------------------------------------------------

_MULTIPLICADORES_DV = (2, 3, 4, 5, 6, 7)


def _calcular_dv(numero: int) -> str:
    """Dígito verificador chileno (módulo 11)."""
    suma = 0
    i = 0
    n = numero
    while n > 0:
        suma += (n % 10) * _MULTIPLICADORES_DV[i % len(_MULTIPLICADORES_DV)]
        n //= 10
        i += 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def generar_rut_valido() -> str:
    """RUT con formato 8 dígitos + espacio + DV (10 caracteres totales)."""
    base = random.randint(0, 99_999_999)
    base_str = str(base).zfill(8)
    return f"{base_str} {_calcular_dv(base)}"


# RUT helpers internos: cada uno devuelve (rut_string_roto, descripcion_corta)
def _rut_sin_espacio() -> tuple[str, str]:
    return generar_rut_valido().replace(" ", ""), "sin espacio antes del DV"


def _rut_espacio_mal() -> tuple[str, str]:
    base = random.randint(10_000_000, 99_999_999)
    bs = str(base)
    dv = _calcular_dv(base)
    return f"{bs[:-1]} {bs[-1]}{dv}", "espacio en posición incorrecta"


def _rut_k_minuscula() -> tuple[str, str]:
    for _ in range(200):
        n = random.randint(10_000_000, 99_999_999)
        if _calcular_dv(n) == "K":
            return f"{n} k", "DV en minúscula (k debe ser K mayúscula)"
    n = random.randint(10_000_000, 99_999_999)
    return f"{n} k", "DV en minúscula"


def _rut_sin_padding() -> tuple[str, str]:
    base = random.randint(100_000, 999_999)  # 6 dígitos sin padding
    return f"{base} {_calcular_dv(base)}", "sin padding de ceros"


def _rut_9_digitos() -> tuple[str, str]:
    base = random.randint(100_000_000, 999_999_999)
    return f"{base} {_calcular_dv(base)}", "9 dígitos en lugar de 8"


_RUT_ERROR_FUNCS = {
    "sin_espacio": _rut_sin_espacio,
    "espacio_mal": _rut_espacio_mal,
    "k_minuscula": _rut_k_minuscula,
    "sin_padding": _rut_sin_padding,
    "9_digitos":   _rut_9_digitos,
}


def generar_rut_con_error() -> tuple[str, str]:
    """Devuelve (rut_con_error, descripcion_error) para arquetipo caotico."""
    func = random.choice(list(_RUT_ERROR_FUNCS.values()))
    return func()


# ---------- glosa con error completo ---------------------------------------
# Cobertura de errores en todos los componentes de una glosa LSC:
#   IOC NNNNNN RUT XXXXXXXX X ID NNNNNN XXX
# Cada builder devuelve un dict {glosa, error_desc, tipo, rojos} donde
# `rojos` es una lista de [start, end) char positions a marcar en rojo.


def _generar_componentes_validos() -> tuple[str, str, str, str]:
    ioc = str(random.randint(0, 999_999)).zfill(6)
    rut = generar_rut_valido()
    id_g = str(random.randint(0, 999_999)).zfill(6)
    ini = "".join(random.choices(string.ascii_uppercase, k=3))
    return ioc, rut, id_g, ini


def _build_glosa(
    parts: list[tuple[str, bool]],
) -> tuple[str, list[tuple[int, int]]]:
    """parts: lista de (texto, marcar_rojo). Devuelve (glosa, segmentos_rojos)."""
    glosa = ""
    rojos: list[tuple[int, int]] = []
    for text, marcar in parts:
        start = len(glosa)
        glosa += text
        if marcar:
            rojos.append((start, len(glosa)))
    return glosa, rojos


def generar_glosa_correcta() -> str:
    """Glosa válida en formato canónico."""
    ioc, rut, id_g, ini = _generar_componentes_validos()
    return f"IOC {ioc} RUT {rut} ID {id_g} {ini}"


# === Errores en palabra "IOC" ===

def _glosa_falta_palabra_ioc() -> dict[str, Any]:
    ioc, rut, id_g, ini = _generar_componentes_validos()
    glosa, rojos = _build_glosa([
        (ioc, True),
        (f" RUT {rut} ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "falta_palabra_ioc",
        "error_desc": "Falta etiqueta 'IOC' al inicio de la glosa",
    }


def _glosa_ioc_minuscula() -> dict[str, Any]:
    ioc, rut, id_g, ini = _generar_componentes_validos()
    glosa, rojos = _build_glosa([
        ("ioc", True),
        (f" {ioc} RUT {rut} ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "ioc_minuscula",
        "error_desc": "Etiqueta 'ioc' en minúscula (debe ser mayúscula)",
    }


# === Errores en número de IOC ===

def _glosa_ioc_5_digitos() -> dict[str, Any]:
    _, rut, id_g, ini = _generar_componentes_validos()
    ioc_5 = str(random.randint(10_000, 99_999))
    glosa, rojos = _build_glosa([
        ("IOC ", False),
        (ioc_5, True),
        (f" RUT {rut} ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "ioc_5_digitos",
        "error_desc": "Número de IOC con 5 dígitos (debe tener 6)",
    }


def _glosa_ioc_7_digitos() -> dict[str, Any]:
    _, rut, id_g, ini = _generar_componentes_validos()
    ioc_7 = str(random.randint(1_000_000, 9_999_999))
    glosa, rojos = _build_glosa([
        ("IOC ", False),
        (ioc_7, True),
        (f" RUT {rut} ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "ioc_7_digitos",
        "error_desc": "Número de IOC con 7 dígitos (debe tener 6)",
    }


def _glosa_ioc_con_letra() -> dict[str, Any]:
    _, rut, id_g, ini = _generar_componentes_validos()
    digits = list(str(random.randint(0, 999_999)).zfill(6))
    pos_letra = random.randint(1, 4)
    digits[pos_letra] = random.choice("ABCDEFGH")
    ioc_bad = "".join(digits)
    pre_letra = ioc_bad[:pos_letra]
    letra = ioc_bad[pos_letra]
    post_letra = ioc_bad[pos_letra + 1:]
    glosa, rojos = _build_glosa([
        ("IOC ", False),
        (pre_letra, False),
        (letra, True),
        (post_letra, False),
        (f" RUT {rut} ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "ioc_con_letra",
        "error_desc": "Número de IOC contiene una letra (debe ser solo dígitos)",
    }


# === Errores en palabra "RUT" ===

def _glosa_falta_palabra_rut() -> dict[str, Any]:
    ioc, rut, id_g, ini = _generar_componentes_validos()
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} ", False),
        (rut, True),
        (f" ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "falta_palabra_rut",
        "error_desc": "Falta etiqueta 'RUT' antes del rol único tributario",
    }


def _glosa_rut_minuscula() -> dict[str, Any]:
    ioc, rut, id_g, ini = _generar_componentes_validos()
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} ", False),
        ("rut", True),
        (f" {rut} ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "rut_minuscula",
        "error_desc": "Etiqueta 'rut' en minúscula (debe ser mayúscula)",
    }


# === Errores intra-RUT (formato del rol) ===

def _glosa_rut_sin_espacio() -> dict[str, Any]:
    ioc, _, id_g, ini = _generar_componentes_validos()
    rut_bad, _ = _rut_sin_espacio()  # "123456789" — sin espacio
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT ", False),
        (rut_bad[:-1], False),
        (rut_bad[-1:], True),  # DV pegado
        (f" ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "rut_sin_espacio",
        "error_desc": "Falta espacio antes del DV (debe estar en posición 9 del RUT)",
    }


def _glosa_rut_espacio_mal() -> dict[str, Any]:
    ioc, _, id_g, ini = _generar_componentes_validos()
    rut_bad, _ = _rut_espacio_mal()  # "1234567 89" — espacio movido
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT ", False),
        (rut_bad[:-3], False),
        (rut_bad[-3:], True),  # 3 últimos chars (espacio + 2 dígitos finales)
        (f" ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "rut_espacio_mal",
        "error_desc": "Espacio dentro del RUT en posición incorrecta (debe estar en posición 9)",
    }


def _glosa_rut_k_minuscula() -> dict[str, Any]:
    ioc, _, id_g, ini = _generar_componentes_validos()
    rut_bad, _ = _rut_k_minuscula()
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT ", False),
        (rut_bad[:-1], False),
        (rut_bad[-1:], True),  # 'k' minúscula
        (f" ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "rut_k_minuscula",
        "error_desc": "DV del RUT en minúscula (debe ser mayúscula)",
    }


def _glosa_rut_sin_padding() -> dict[str, Any]:
    ioc, _, id_g, ini = _generar_componentes_validos()
    rut_bad, _ = _rut_sin_padding()
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT ", False),
        (rut_bad, True),  # RUT entero — falta padding
        (f" ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "rut_sin_padding",
        "error_desc": "RUT base con menos de 8 dígitos (debe tener 8)",
    }


def _glosa_rut_9_digitos() -> dict[str, Any]:
    ioc, _, id_g, ini = _generar_componentes_validos()
    rut_bad, _ = _rut_9_digitos()
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT ", False),
        (rut_bad[:1], True),  # primer dígito (uno de más)
        (rut_bad[1:], False),
        (f" ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "rut_9_digitos",
        "error_desc": "RUT base con 9 dígitos (debe tener 8)",
    }


# === Errores en palabra "ID" ===

def _glosa_falta_palabra_id() -> dict[str, Any]:
    ioc, rut, id_g, ini = _generar_componentes_validos()
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT {rut} ", False),
        (id_g, True),
        (f" {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "falta_palabra_id",
        "error_desc": "Falta etiqueta 'ID' antes del número (debe ir tras RUT)",
    }


def _glosa_id_minuscula() -> dict[str, Any]:
    ioc, rut, id_g, ini = _generar_componentes_validos()
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT {rut} ", False),
        ("id", True),
        (f" {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "id_minuscula",
        "error_desc": "Etiqueta 'id' en minúscula (debe ser mayúscula)",
    }


# === Errores en número de ID ===

def _glosa_id_5_digitos() -> dict[str, Any]:
    ioc, rut, _, ini = _generar_componentes_validos()
    id_5 = str(random.randint(10_000, 99_999))
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT {rut} ID ", False),
        (id_5, True),
        (f" {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "id_5_digitos",
        "error_desc": "Número de ID con 5 dígitos (debe tener 6)",
    }


def _glosa_id_7_digitos() -> dict[str, Any]:
    ioc, rut, _, ini = _generar_componentes_validos()
    id_7 = str(random.randint(1_000_000, 9_999_999))
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT {rut} ID ", False),
        (id_7, True),
        (f" {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "id_7_digitos",
        "error_desc": "Número de ID con 7 dígitos (debe tener 6)",
    }


# === Errores en iniciales ===

def _glosa_solo_2_iniciales() -> dict[str, Any]:
    ioc, rut, id_g, _ = _generar_componentes_validos()
    ini_2 = "".join(random.choices(string.ascii_uppercase, k=2))
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT {rut} ID {id_g} ", False),
        (ini_2, True),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "solo_2_iniciales",
        "error_desc": "Iniciales con 2 letras (debe tener 3)",
    }


def _glosa_4_iniciales() -> dict[str, Any]:
    ioc, rut, id_g, _ = _generar_componentes_validos()
    ini_4 = "".join(random.choices(string.ascii_uppercase, k=4))
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT {rut} ID {id_g} ", False),
        (ini_4, True),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "4_iniciales",
        "error_desc": "Iniciales con 4 letras (debe tener 3)",
    }


def _glosa_iniciales_minuscula() -> dict[str, Any]:
    ioc, rut, id_g, _ = _generar_componentes_validos()
    ini_lower = "".join(random.choices(string.ascii_lowercase, k=3))
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} RUT {rut} ID {id_g} ", False),
        (ini_lower, True),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "iniciales_minuscula",
        "error_desc": "Iniciales en minúscula (deben ser mayúsculas)",
    }


# === Errores de orden ===

def _glosa_rut_antes_de_ioc() -> dict[str, Any]:
    ioc, rut, id_g, ini = _generar_componentes_validos()
    # Esperado: IOC N RUT N ID N XXX | Roto: RUT N IOC N ID N XXX
    glosa, rojos = _build_glosa([
        ("RUT", True),
        (f" {rut} ", False),
        ("IOC", True),
        (f" {ioc} ID {id_g} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "rut_antes_de_ioc",
        "error_desc": "Orden incorrecto: 'RUT' antes que 'IOC' (orden esperado: IOC, RUT, ID, iniciales)",
    }


def _glosa_id_antes_de_rut() -> dict[str, Any]:
    ioc, rut, id_g, ini = _generar_componentes_validos()
    # Roto: IOC N ID N RUT N XXX
    glosa, rojos = _build_glosa([
        (f"IOC {ioc} ", False),
        ("ID", True),
        (f" {id_g} ", False),
        ("RUT", True),
        (f" {rut} {ini}", False),
    ])
    return {
        "glosa": glosa, "rojos": rojos, "tipo": "id_antes_de_rut",
        "error_desc": "Orden incorrecto: 'ID' antes que 'RUT' (orden esperado: IOC, RUT, ID, iniciales)",
    }


GLOSA_ERROR_BUILDERS: dict[str, Any] = {
    # Etiqueta IOC
    "falta_palabra_ioc":    _glosa_falta_palabra_ioc,
    "ioc_minuscula":        _glosa_ioc_minuscula,
    # Número IOC
    "ioc_5_digitos":        _glosa_ioc_5_digitos,
    "ioc_7_digitos":        _glosa_ioc_7_digitos,
    "ioc_con_letra":        _glosa_ioc_con_letra,
    # Etiqueta RUT
    "falta_palabra_rut":    _glosa_falta_palabra_rut,
    "rut_minuscula":        _glosa_rut_minuscula,
    # Formato RUT (5 existentes)
    "rut_sin_espacio":      _glosa_rut_sin_espacio,
    "rut_espacio_mal":      _glosa_rut_espacio_mal,
    "rut_k_minuscula":      _glosa_rut_k_minuscula,
    "rut_sin_padding":      _glosa_rut_sin_padding,
    "rut_9_digitos":        _glosa_rut_9_digitos,
    # Etiqueta ID
    "falta_palabra_id":     _glosa_falta_palabra_id,
    "id_minuscula":         _glosa_id_minuscula,
    # Número ID
    "id_5_digitos":         _glosa_id_5_digitos,
    "id_7_digitos":         _glosa_id_7_digitos,
    # Iniciales
    "solo_2_iniciales":     _glosa_solo_2_iniciales,
    "4_iniciales":          _glosa_4_iniciales,
    "iniciales_minuscula":  _glosa_iniciales_minuscula,
    # Orden
    "rut_antes_de_ioc":     _glosa_rut_antes_de_ioc,
    "id_antes_de_rut":      _glosa_id_antes_de_rut,
}

TIPOS_ERROR_GLOSA: tuple[str, ...] = tuple(GLOSA_ERROR_BUILDERS.keys())


def generar_glosa_con_error(forzar: str | None = None) -> dict[str, Any]:
    """Devuelve {glosa, error_desc, tipo, rojos} con un error aleatorio o forzado."""
    tipo = forzar if forzar else random.choice(TIPOS_ERROR_GLOSA)
    builder = GLOSA_ERROR_BUILDERS[tipo]
    return builder()


# ---------- helpers de generación ------------------------------------------


def _generar_ioc() -> str:
    return str(random.randint(0, 999_999)).zfill(6)


def _generar_id_glosa() -> str:
    return str(random.randint(0, 999_999)).zfill(6)


def _generar_iniciales() -> str:
    return "".join(random.choices(string.ascii_uppercase, k=3))


def _otro_persona_nombre(self_id: int) -> str:
    candidatos = [v["nombre"] for k, v in PERFILES_PERSONA.items() if k != self_id]
    return random.choice(candidatos)


# ---------- simulación de respuesta ----------------------------------------


def simular_respuesta(
    persona_id: int,
    contenido_correo_recibido: str,
    gmail_message_id_original: str,
) -> dict[str, Any]:
    """Devuelve {responde, contenido, dias_demora, tipo} sin persistir nada."""
    perfil = PERFILES_PERSONA.get(persona_id)
    if perfil is None:
        return {"responde": False, "contenido": "", "dias_demora": 0,
                "tipo": "sin_perfil"}

    arquetipo = perfil["arquetipo"]
    nombre = perfil["nombre"]
    ioc = _generar_ioc()
    id_glosa = _generar_id_glosa()
    iniciales = _generar_iniciales()

    if arquetipo == "certero":
        rut = generar_rut_valido()
        contenido = (
            f"Hola,\n\n"
            f"Listo, ya corregí. Detalle:\n"
            f"IOC: {ioc}\n"
            f"RUT: {rut}\n"
            f"ID: {id_glosa}\n"
            f"Resp: {iniciales}\n\n"
            f"Saludos,\n{nombre}"
        )
        return {"responde": True, "contenido": contenido, "dias_demora": 0,
                "tipo": "certero_ok"}

    if arquetipo == "mixto":
        if random.random() < 0.70:
            rut = generar_rut_valido()
            contenido = (
                f"Hola, va la corrección:\n"
                f"IOC {ioc} - RUT {rut} - ID {id_glosa} - Resp {iniciales}\n\n"
                f"Saludos."
            )
            return {"responde": True, "contenido": contenido, "dias_demora": 0,
                    "tipo": "mixto_ok"}
        rut = generar_rut_valido()
        contenido = (
            f"Hola, te paso lo que tengo a mano:\n"
            f"IOC: {ioc}\n"
            f"RUT: {rut}\n\n"
            f"Lo que falta lo busco y te aviso."
        )
        return {"responde": True, "contenido": contenido, "dias_demora": 1,
                "tipo": "mixto_incompleto"}

    if arquetipo == "caotico":
        rama = random.choices(_RAMAS_CAOTICO, weights=_PESOS_CAOTICO, k=1)[0]
        if rama == "mal":
            rut_malo, _err = generar_rut_con_error()
            contenido = (
                f"Hola, ahí va:\n"
                f"IOC {ioc} RUT {rut_malo} ID {id_glosa} {iniciales}\n\n"
                f"{nombre}"
            )
            return {"responde": True, "contenido": contenido, "dias_demora": 0,
                    "tipo": "caotico_mal"}
        if rama == "pelota":
            otro = _otro_persona_nombre(persona_id)
            contenido = (
                f"Hola, esto lo lleva {otro}, le pregunté a ella que se "
                f"encarga del tema. Saludos."
            )
            return {"responde": True, "contenido": contenido, "dias_demora": 1,
                    "tipo": "caotico_pelota"}
        if rama == "tarde":
            rut = generar_rut_valido()
            contenido = (
                f"Hola, disculpa la demora, recién pude verlo. "
                f"Va la corrección:\n"
                f"IOC {ioc} - RUT {rut} - ID {id_glosa} - Resp {iniciales}\n\n"
                f"Saludos, {nombre}"
            )
            return {"responde": True, "contenido": contenido, "dias_demora": 3,
                    "tipo": "caotico_tarde"}
        # ignora
        return {"responde": False, "contenido": "", "dias_demora": 0,
                "tipo": "caotico_ignora"}

    return {"responde": False, "contenido": "", "dias_demora": 0,
            "tipo": "desconocido"}


# ---------- persistencia ---------------------------------------------------


def _persona_que_responde(mensaje_agente: dict) -> int | None:
    """Primer destinatario (TO o CC) que tiene perfil simulable."""
    candidatos = list(mensaje_agente.get("destinatarios_to") or [])
    candidatos += list(mensaje_agente.get("destinatarios_cc") or [])
    for pid in candidatos:
        if pid in PERFILES_PERSONA:
            return pid
    return None


def _persistir_respuesta(
    *,
    trabajo_id: int,
    remitente_id: int,
    contenido: str,
    dias_demora: int,
    asunto_referencia: str,
) -> int:
    timestamp = datetime.now() - timedelta(days=dias_demora)
    sim_id = f"sim_{uuid.uuid4().hex[:16]}"
    asunto = f"Re: {asunto_referencia}"
    sql = """
        INSERT INTO mensajes (
            trabajo_id, remitente_id, destinatarios_to, destinatarios_cc,
            asunto, contenido, gmail_message_id, timestamp, enviado_at,
            zona_al_enviar
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
        RETURNING mensaje_id
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            sql,
            (
                trabajo_id, remitente_id, [AGENTE_ID], [],
                asunto, contenido, sim_id, timestamp, timestamp,
            ),
        )
        return cur.fetchone()[0]


def simular_respuestas_a_todos_pendientes() -> list[dict[str, Any]]:
    """Para cada último envío del agente sin respuesta posterior, simula."""
    sql_pendientes = """
        SELECT DISTINCT ON (trabajo_id)
               mensaje_id, trabajo_id, destinatarios_to, destinatarios_cc,
               asunto, contenido, gmail_message_id, enviado_at
        FROM   mensajes
        WHERE  remitente_id = %s AND gmail_message_id IS NOT NULL
               AND gmail_message_id NOT LIKE 'sim_%%'
        ORDER BY trabajo_id, enviado_at DESC
    """
    sql_respuesta_existe = """
        SELECT 1 FROM mensajes
        WHERE  trabajo_id = %s
               AND remitente_id <> %s
               AND timestamp > %s
        LIMIT 1
    """

    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql_pendientes, (AGENTE_ID,))
        agente_msgs = cur.fetchall()

    resultados: list[dict[str, Any]] = []
    for ag in agente_msgs:
        # ¿ya hay respuesta para este hilo?
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(sql_respuesta_existe, (ag["trabajo_id"], AGENTE_ID, ag["enviado_at"]))
            ya_respondido = cur.fetchone() is not None

        if ya_respondido:
            resultados.append({
                "trabajo_id": ag["trabajo_id"],
                "estado": "respuesta_ya_existente",
                "tipo": None,
                "respondio_id": None,
                "mensaje_simulado_id": None,
            })
            continue

        responder_id = _persona_que_responde(ag)
        if responder_id is None:
            resultados.append({
                "trabajo_id": ag["trabajo_id"],
                "estado": "sin_perfil_simulable",
                "tipo": None,
                "respondio_id": None,
                "mensaje_simulado_id": None,
            })
            continue

        sim = simular_respuesta(responder_id, ag["contenido"], ag["gmail_message_id"])
        if not sim["responde"]:
            resultados.append({
                "trabajo_id": ag["trabajo_id"],
                "estado": "no_respondio",
                "tipo": sim["tipo"],
                "respondio_id": responder_id,
                "mensaje_simulado_id": None,
            })
            continue

        sim_msg_id = _persistir_respuesta(
            trabajo_id=ag["trabajo_id"],
            remitente_id=responder_id,
            contenido=sim["contenido"],
            dias_demora=sim["dias_demora"],
            asunto_referencia=ag["asunto"],
        )
        resultados.append({
            "trabajo_id": ag["trabajo_id"],
            "estado": "respondio",
            "tipo": sim["tipo"],
            "respondio_id": responder_id,
            "mensaje_simulado_id": sim_msg_id,
            "contenido": sim["contenido"],
        })

    return resultados
