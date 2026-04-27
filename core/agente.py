"""Agente que redacta correos de seguimiento usando GPT-4o-mini.

`generar_correo(trabajo)` recibe el dict de `evaluar_trabajo` y devuelve
un dict listo para persistir en la tabla `mensajes`:
    {trabajo_id, remitente_id, destinatarios_to, destinatarios_cc,
     asunto, contenido}

Las direcciones se manejan como `persona_id` (no como email): se asume
que toda persona-destinataria existe en la tabla `personas`. Los jefes
de área son personas con rol_id correspondiente al rol "jefe_area".
"""

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.db import get_connection

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

MODEL = "gpt-4o-mini"
TEMPERATURA = 0.4
AGENTE_PERSONA_ID = 0

SUBJECT_POR_ZONA: dict[str, str] = {
    "p97": "Recordatorio: {descripcion}",
    "p84": "Recordatorio - Deadline próximo: {descripcion}",
    "p50": "URGENTE - Deadline en riesgo: {descripcion}",
    "critico": "Solicito apoyo - Riesgo de incumplimiento: {descripcion}",
}

_DIAS_ES = [
    "lunes", "martes", "miércoles", "jueves",
    "viernes", "sábado", "domingo",
]
_MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _fecha_humana(dt) -> str:
    """Devuelve 'martes 28 de abril a las 12:00' (incluye hora siempre)."""
    return (
        f"{_DIAS_ES[dt.weekday()]} {dt.day} de {_MESES_ES[dt.month - 1]} "
        f"a las {dt.strftime('%H:%M')}"
    )

SYSTEM_PROMPT = """\
Sos un coordinador de equipo del área regulatoria de un banco chileno.
Escribís correos para mantener entregables al día con tus colegas.

VOZ: la de un coordinador humano que conoce a sus colegas. Profesional,
cordial, claro. Español chileno-corporativo, NO acartonado. Imaginá cómo
le escribiría a un compañero alguien que se preocupa de que las cosas
salgan bien sin pisar a nadie.

PROHIBIDO mencionar vocabulario técnico interno del sistema. NUNCA usás
los términos: "lead time", "estadística", "estadísticamente",
"probabilidad", "probable", "percentil", "sigma", "varianza", "margen",
"holgura", "deadline" (decí "plazo" o nombrá la fecha), "horas hábiles",
"horas restantes", "tiempo disponible", "dentro de N horas". Tampoco
hacés cuentas explícitas tipo "quedan X horas". Esos son conceptos
internos; en el correo solo aparecen fechas concretas.

FORMATO:
- Devolvés SOLO el cuerpo del correo: sin asunto, sin firma de bot, sin
  meta-comentarios, sin placeholders entre corchetes (tipo [Nombre]).
- Estructura: saludo + 1-2 frases de contexto (qué tarea es, fecha del
  plazo) + pedido concreto + cierre amable.
- Si no conocés el nombre de la persona destinataria (jefatura genérica),
  usás saludo natural: "Estimada jefatura del área X", "Hola equipo".

ZONAS — cuatro niveles de urgencia interna que afectan el TONO pero
NUNCA se nombran en el correo:

1. "p97" — el plazo está holgado, es solo un ping para tener la tarea
   en el radar. Tono casual, sin urgencia.
   Ejemplo: "Te escribo para que tengamos en el radar la confirmación
   de las cuentas TC, que vence el martes 28."

2. "p84" — el plazo se está acercando, todavía hay tiempo razonable.
   Recordatorio firme y amable, sin alarmismo.
   Ejemplo: "Te escribo para coordinar la entrega de las glosas LSC
   antes del jueves 30."

3. "p50" — el plazo aprieta y conviene moverse pronto. URGENCIA
   CONTROLADA: pedís coordinación o avance, NO suena alarmista.
   Ejemplo: "Te escribo para coordinar la entrega de X antes del
   viernes 2 de mayo. ¿Podemos sincronizar para asegurar que salga?"
   NO digás "quedan pocas horas", "el plazo se acaba", "urgente".

4. "critico" — el correo va al JEFE DEL ÁREA pidiendo apoyo. La persona
   asignada va en copia. Pedido humano y franco, NO cuantitativo.
   SALUDO FORMAL obligatorio (NUNCA "Hola," seco): empezás con
   "Estimada jefatura del área X," o "Hola jefatura del área X,".
   Cordial pero respetuoso del rol.
   FECHA DEL PLAZO obligatoria en el cuerpo: es la información más
   importante del correo. Mencionala en formato humano ("antes del
   martes 5 de mayo", "para el jueves 30 a las 18:00").
   Ejemplo: "Estimada jefatura del área LSC, quería pedirte apoyo
   para empujar la validación de las glosas con Yolanda antes del
   jueves 30 de abril. El plazo nos está quedando muy ajustado y
   queremos coordinar para no fallar la entrega. Agradezco tu apoyo."
   El argumento es de gestión y coordinación, no de estadística.
   NUNCA digás "no llegará a entregar", "según su ritmo habitual",
   o cualquier referencia a métricas o cálculos.

NIVEL DE ROCE — afecta solo el registro:
- "bajo": tratamiento "tú", directo y conciso, sin excesos.
- "medio": equilibrado, formal pero cercano. "Tú" o "usted" según
  lo que suene natural.
- "alto": tratamiento "usted", máxima cordialidad y formalidad,
  evitás cualquier presión percibida.

ROL del destinatario directo:
- "ejecutor" (no-critico): le pedís ejecutar o responder.
- "jefe" (no-critico): le pedís priorización, destrabe o visibilidad,
  no que ejecute.
- En "critico" siempre te dirigís al jefe del área.

FECHAS: las mencionás de forma natural ("el martes 28 de abril", "antes
del viernes 2 de mayo", "para el jueves 30"). Si la hora es relevante
(plazos a media jornada) la incluís ("el martes 28 al mediodía"). NO
mencionás cuántas horas quedan ni hacés cuentas.
"""


def _obtener_jefe_id(area_nombre: str | None) -> int | None:
    """Devuelve el persona_id del jefe del área (rol = jefe_area)."""
    if area_nombre is None:
        return None
    sql = """
        SELECT  p.persona_id
        FROM    personas p
        JOIN    roles r ON r.rol_id  = p.rol_id
        JOIN    areas a ON a.area_id = p.area_id
        WHERE   r.nombre = 'jefe_area' AND a.nombre = %s
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, (area_nombre,))
        row = cur.fetchone()
    return row[0] if row else None


def _decidir_routing(
    trabajo: dict[str, Any],
) -> tuple[list[int], list[int], str]:
    """Devuelve (destinatarios_to, destinatarios_cc, nombre_destinatario_directo).

    - critico: TO = jefe del área, CC = persona asignada.
    - p97/p84/p50: TO = persona asignada. CC al jefe según nivel_roce:
        bajo  → nunca CC (excepto en critico).
        medio → CC desde p84.
        alto  → CC siempre.
    """
    zona = trabajo["zona"]
    nivel_roce = trabajo["nivel_roce"]
    area = trabajo["area"]
    persona_id = trabajo["persona_id"]
    persona_nombre = trabajo["persona"]
    jefe_id = _obtener_jefe_id(area)

    if zona == "critico":
        if jefe_id is None:
            return [persona_id], [], persona_nombre
        return [jefe_id], [persona_id], f"jefe del área {area}"

    cc: list[int] = []
    if jefe_id is not None:
        if nivel_roce == "alto":
            cc = [jefe_id]
        elif nivel_roce == "medio" and zona in ("p84", "p50"):
            cc = [jefe_id]
    return [persona_id], cc, persona_nombre


def _user_prompt(trabajo: dict[str, Any], destinatario_nombre: str) -> str:
    fecha = _fecha_humana(trabajo["deadline"])
    es_critico = trabajo["zona"] == "critico"
    nota_critico = (
        f"\nNOTA: estás escribiendo al JEFE DEL ÁREA. "
        f"La persona asignada ({trabajo['persona']}) va en copia.\n"
        if es_critico
        else ""
    )
    return f"""\
Generá el cuerpo del correo para el siguiente caso.

DESTINATARIO PRINCIPAL: {destinatario_nombre}{nota_critico}

PERSONA ASIGNADA AL TRABAJO
- Nombre: {trabajo['persona']}
- Rol: {trabajo['rol']}
- Área: {trabajo['area']}
- Nivel de roce: {trabajo['nivel_roce']}

TRABAJO
- Descripción: {trabajo['descripcion']}
- Plazo: {fecha}

ZONA: {trabajo['zona']}
"""


def generar_correo(trabajo: dict[str, Any]) -> dict[str, Any]:
    """Devuelve el dict listo para persistir en `mensajes`."""
    destinatarios_to, destinatarios_cc, destinatario_nombre = _decidir_routing(trabajo)
    asunto = SUBJECT_POR_ZONA[trabajo["zona"]].format(
        descripcion=trabajo["descripcion"]
    )

    chat = ChatOpenAI(model=MODEL, temperature=TEMPERATURA)
    resp = chat.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_user_prompt(trabajo, destinatario_nombre)),
        ]
    )
    contenido = resp.content.strip()

    return {
        "trabajo_id": trabajo["trabajo_id"],
        "remitente_id": AGENTE_PERSONA_ID,
        "destinatarios_to": destinatarios_to,
        "destinatarios_cc": destinatarios_cc,
        "asunto": asunto,
        "contenido": contenido,
        "zona": trabajo["zona"],
    }
