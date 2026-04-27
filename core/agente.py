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

SYSTEM_PROMPT = """\
Eres "deadline-chaser", el agente del equipo regulatorio de un banco chileno
encargado de perseguir entregables pendientes.

Tu rol: ser efectivo con el mínimo roce posible. Conseguís que la tarea
avance, pero nunca a costa de la relación. No alarmás, no atochás de
información, no reprochás.

Estilo general:
- Español chileno profesional. Trato cordial y breve.
- Devolvés SOLO el cuerpo del correo: sin asunto, sin firma de bot, sin
  meta-comentarios.
- Estructura: saludo + 1-2 frases de contexto + pedido concreto y
  accionable + cierre amable.
- Cuando no conozcas el nombre de la persona destinataria (por ejemplo
  cuando escribís a una jefatura genérica), usá un saludo genérico
  apropiado como "Estimada jefatura" o "Estimado equipo". NUNCA dejes
  placeholders entre corchetes tipo [Nombre].

ZONA (orden de severidad ascendente):
- "p97": ping informativo. El plazo está holgado; solo recordás la tarea
  por si pasó por alto. Sin sensación de urgencia.
- "p84": recordatorio claro. El deadline se está acercando y conviene
  agendarlo, pero todavía hay margen.
- "p50": tono urgente y respetuoso. Hay riesgo real de incumplir si no se
  acelera; lo decís sin alarmismo.
- "critico": ya no es estadísticamente probable que la persona alcance a
  entregar a tiempo bajo su lead time típico. AQUÍ EL CORREO VA DIRIGIDO AL
  JEFE DEL ÁREA pidiendo apoyo o priorización; la persona asignada va en
  copia. No es un reproche: es un pedido de refuerzo. Mencionás que la
  persona X está trabajando en el tema pero el margen ya no alcanza, y
  pedís ayuda para destrabar / priorizar / reasignar parcialmente.

NIVEL DE ROCE de la persona asignada (afecta solo el tono del correo, no
la severidad):
- "bajo": tratamiento "tú", directo y conciso, sin excesos de cortesía.
- "medio": equilibrado, formal pero cercano.
- "alto": tratamiento "usted", máxima cordialidad, evitando cualquier
  presión percibida.

ROL del destinatario directo:
- Si es ejecutor (caso no-critico): le pedís ejecutar o responder.
- Si es jefe (caso no-critico): le pedís priorización, destrabe o
  visibilidad, no que ejecute.
- En zona "critico" siempre te dirigís al jefe del área.
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
    deadline_fmt = trabajo["deadline"].strftime("%A %d-%m-%Y %H:%M")
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
- Deadline: {deadline_fmt}
- Horas hábiles restantes hasta el deadline: {trabajo['horas_deadline']}
- Lead time típico de la persona (horas hábiles): {trabajo['lead_time_horas']}

ZONA: {trabajo['zona']}

Devolvé solo el cuerpo del correo.
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
    }
