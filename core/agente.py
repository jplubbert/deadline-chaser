"""Agente que redacta correos de seguimiento usando GPT-4o-mini.

Arquitectura:
- ROUTING (TO/CC), asunto, tono, intención: lógica determinística en Python.
  El LLM nunca decide a quién mandar el correo ni reglas de escalamiento.
- REDACCIÓN del cuerpo: el LLM. Recibe destinatario ya resuelto + intención
  + tratamiento + tono. No ve "zona" ni "tipo_correo" en sus etiquetas
  internas; solo descripciones en lenguaje natural.

`generar_correo(trabajo, tipo_correo, contexto_extra)` devuelve un dict
listo para persistir en la tabla `mensajes`:
    {trabajo_id, remitente_id, destinatarios_to, destinatarios_cc,
     asunto, contenido, zona, tipo_correo}
"""

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from core.db import get_connection
from core.excel_generator import generar_excel_adjunto

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

MODEL = "gpt-4o-mini"
TEMPERATURA = 0.4
AGENTE_PERSONA_ID = 0

REGTECH_API_URL = os.environ.get("REGTECH_API_URL", "http://127.0.0.1:8001")


# --------------------------------------------------------------------------
# TOOL: PREDICTOR DE CRONOGRAMAS LEGALES (regtech-rag-chile)
# --------------------------------------------------------------------------

@tool
def predecir_cronograma_legal(caso_data: dict) -> dict:
    """Consulta el predictor del proyecto regtech-rag-chile y devuelve el
    cronograma legal de un caso bajo Ley 20.009.

    Recibe un dict con datos del caso (RUT cliente, fecha desconocimiento,
    monto operación, autenticación reforzada, etc.) y devuelve la lista de
    fechas críticas (bloqueo de tarjeta, primer pago, segundo pago, demanda)
    junto con su fundamento legal (artículo + inciso) extraído vía RAG.

    El servicio HTTP debe estar corriendo en REGTECH_API_URL (default
    http://127.0.0.1:8001).
    """
    response = httpx.post(
        f"{REGTECH_API_URL}/predecir-cronograma",
        json=caso_data,
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


# --------------------------------------------------------------------------
# ROUTING DETERMINÍSTICO
# --------------------------------------------------------------------------

# Matriz de routing. Lista ordenada de (predicado, resultado).
# Match con la primera regla cuyo predicado se cumple. Predicados parciales
# matchean cualquier valor en las claves no especificadas.
ROUTING_MATRIX: list[tuple[dict[str, str], dict[str, Any]]] = [
    # Tipo override: aclaracion_errores SIEMPRE va a la persona, sin CC
    ({"tipo_correo": "aclaracion_errores"},
     {"to": "persona", "cc": []}),
    # Tipo override: derivado SIEMPRE va a la persona, sin CC
    ({"tipo_correo": "derivado_volver_a_la_misma"},
     {"to": "persona", "cc": []}),
    # Critico (primer_envio o recordatorio): jefe TO, persona en CC
    ({"tipo_correo": "primer_envio", "zona": "critico"},
     {"to": "jefe", "cc": ["persona"]}),
    ({"tipo_correo": "recordatorio", "zona": "critico"},
     {"to": "jefe", "cc": ["persona"]}),
    # Roce alto (no-critico): persona TO, jefe en CC siempre
    ({"tipo_correo": "primer_envio", "nivel_roce": "alto"},
     {"to": "persona", "cc": ["jefe"]}),
    ({"tipo_correo": "recordatorio", "nivel_roce": "alto"},
     {"to": "persona", "cc": ["jefe"]}),
    # Roce medio + zonas tensas (p84/p50): persona TO, jefe en CC
    ({"tipo_correo": "primer_envio", "zona": "p84", "nivel_roce": "medio"},
     {"to": "persona", "cc": ["jefe"]}),
    ({"tipo_correo": "primer_envio", "zona": "p50", "nivel_roce": "medio"},
     {"to": "persona", "cc": ["jefe"]}),
    ({"tipo_correo": "recordatorio", "zona": "p84", "nivel_roce": "medio"},
     {"to": "persona", "cc": ["jefe"]}),
    ({"tipo_correo": "recordatorio", "zona": "p50", "nivel_roce": "medio"},
     {"to": "persona", "cc": ["jefe"]}),
]

ROUTING_DEFAULT: dict[str, Any] = {"to": "persona", "cc": []}


def _lookup_routing(
    tipo_correo: str, zona: str, nivel_roce: str | None
) -> dict[str, Any]:
    contexto = {"tipo_correo": tipo_correo, "zona": zona, "nivel_roce": nivel_roce}
    for predicado, resultado in ROUTING_MATRIX:
        if all(contexto.get(k) == v for k, v in predicado.items()):
            return resultado
    return ROUTING_DEFAULT


def _obtener_jefe_id(area_nombre: str | None) -> int | None:
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


def _resolver_routing_a_ids(
    routing: dict[str, Any], trabajo: dict[str, Any]
) -> tuple[list[int], list[int]]:
    persona_id = trabajo["persona_id"]
    jefe_id = _obtener_jefe_id(trabajo.get("area"))

    def _resolver(token: str) -> int | None:
        if token == "persona":
            return persona_id
        if token == "jefe":
            return jefe_id
        return None

    to_id = _resolver(routing["to"]) or persona_id  # fallback persona
    cc_ids = [tid for token in routing["cc"] if (tid := _resolver(token)) is not None]
    return [to_id], cc_ids


# --------------------------------------------------------------------------
# DESCRIPTORES PARA EL LLM (sin etiquetas internas)
# --------------------------------------------------------------------------

TRATAMIENTO_POR_ROCE: dict[str, str] = {
    "bajo":  "tutear, directo y conciso, sin excesos de cortesía",
    "medio": "balanceado, formal pero cercano",
    "alto":  "tratamiento de usted, máxima cordialidad y formalidad",
}

URGENCIA_POR_ZONA: dict[str, str] = {
    "p97":     "ping informativo casual, sin urgencia",
    "p84":     "recordatorio firme y amable, el plazo se acerca pero hay margen",
    "p50":     "urgencia controlada, el plazo aprieta — pedís coordinación, sin alarmismo",
    "critico": "pedido franco de apoyo, el plazo está comprometido",
}

INTENCION_POR_TIPO: dict[str, str] = {
    "primer_envio":               "Es el primer correo sobre esta tarea. Presentás el tema y pedís lo que corresponda según el destinatario.",
    "recordatorio":               "Ya escribiste antes y la persona no respondió. Recordás brevemente el tema sin reproche y reiterás el pedido.",
    "aclaracion_errores":         "La persona respondió pero su respuesta tenía errores de formato. Le pedís corregirlos citando los errores específicos. NO reproches, NO alarmismo.",
    "derivado_volver_a_la_misma": "La persona te derivó la responsabilidad a otra. Le explicás que como responsable formal, necesitás que la respuesta venga directamente de su lado. Cordial pero firme.",
}

SUBJECT_POR_TIPO_CORREO: dict[str, str] = {
    "aclaracion_errores":         "Aclaración solicitada: {descripcion}",
    "derivado_volver_a_la_misma": "Seguimiento: {descripcion}",
}

SUBJECT_POR_ZONA: dict[str, str] = {
    "p97":     "Recordatorio: {descripcion}",
    "p84":     "Recordatorio - Deadline próximo: {descripcion}",
    "p50":     "URGENTE - Deadline en riesgo: {descripcion}",
    "critico": "Solicito apoyo - Riesgo de incumplimiento: {descripcion}",
}


def _calcular_asunto(tipo_correo: str, trabajo: dict[str, Any]) -> str:
    if tipo_correo in SUBJECT_POR_TIPO_CORREO:
        plantilla = SUBJECT_POR_TIPO_CORREO[tipo_correo]
    else:
        plantilla = SUBJECT_POR_ZONA[trabajo["zona"]]
    return plantilla.format(descripcion=trabajo["descripcion"])


# --------------------------------------------------------------------------
# FECHA HUMANA
# --------------------------------------------------------------------------

_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _fecha_humana(dt) -> str:
    return (
        f"{_DIAS_ES[dt.weekday()]} {dt.day} de {_MESES_ES[dt.month - 1]} "
        f"a las {dt.strftime('%H:%M')}"
    )


# --------------------------------------------------------------------------
# PROMPT PARA EL LLM (solo redacción)
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Sos un coordinador de equipo del área regulatoria de un banco chileno.
Escribís correos para mantener entregables al día con tus colegas.

VOZ
- Coordinador humano, cordial, claro. Profesional pero NO acartonado.
- Español chileno-corporativo.

PROHIBIDO
- Mencionar vocabulario técnico interno: "lead time", "estadística",
  "estadísticamente", "probabilidad", "probable", "percentil", "sigma",
  "varianza", "margen", "holgura", "deadline" (decí "plazo" o nombrá la
  fecha), "horas hábiles", "horas restantes", "tiempo disponible",
  "dentro de N horas". NO hacés cuentas explícitas tipo "quedan X horas".
- Dejar placeholders entre corchetes ([Nombre], [fecha], etc.).

FORMATO
- Devolvés SOLO el cuerpo del correo: sin asunto, sin firma de bot,
  sin meta-comentarios.
- Estructura por defecto: saludo + 1-2 frases de contexto + pedido
  concreto + cierre amable.

DESTINATARIO Y ROUTING — NO TE TOCA DECIDIRLOS.
- El orquestador resuelve a quién va el correo y te lo informa en el
  campo DESTINATARIO PRINCIPAL del user prompt.
- Si dice un nombre de persona, escribís a esa persona con saludo
  personalizado ("Hola Yolanda,", "Estimado Carlos,").
- Si dice "jefatura del área X", usás saludo formal a esa jefatura
  ("Estimada jefatura del área LSC,").
- Si el user prompt incluye PERSONA EN COPIA, mencionás a esa persona
  brevemente en el cuerpo (porque la copia la va a leer también).
  Si no hay PERSONA EN COPIA, no mencionás nada de copias.
- NUNCA cambiás el destinatario. NUNCA escalás al jefe por tu cuenta.

INTENCIÓN, TRATAMIENTO Y TONO
- INTENCIÓN: el orquestador te pasa una descripción de qué pretendés
  con este correo. Tu cuerpo cumple esa intención.
- TRATAMIENTO: cómo te dirigís (tutear / usted / balanceado).
- TONO: cómo se siente el correo (casual / firme / urgente / pedido
  de apoyo). No inventes urgencia ni la reduzcas.

ESTRUCTURA POR INTENCIÓN
- Primer envío: saludo + presentación breve del tema + pedido + cierre.
- Recordatorio: saludo + recordás el tema sin reproche + reiterás el
  pedido + cierre.
- Pedido de corrección (errores en respuesta): saludo + agradecés la
  respuesta brevemente + citás cada error con el dato concreto + pedís
  corrección + cierre. NUNCA reproche.
- Devolver responsabilidad (derivación): saludo + reconocés que la
  otra persona está al tanto + explicás que como destinatario sos
  el responsable formal y necesitás respuesta directa + cierre.

FECHAS — las mencionás de forma natural ("el martes 28 de abril",
"antes del viernes 2 de mayo", "para el jueves 30"). Si la hora es
relevante (plazos a media jornada) la incluís ("el martes 28 al
mediodía"). NO mencionás cuántas horas quedan.
"""


def _user_prompt(
    trabajo: dict[str, Any],
    destinatario_principal: str,
    persona_en_copia: str | None,
    intencion: str,
    tratamiento: str,
    tono: str,
    contexto_extra: dict[str, Any] | None,
    nombre_adjunto: str | None = None,
) -> str:
    fecha = _fecha_humana(trabajo["deadline"])

    bloque_copia = (
        f"PERSONA EN COPIA: {persona_en_copia} (mencionar brevemente en el cuerpo)\n"
        if persona_en_copia
        else ""
    )

    bloque_adjunto = (
        f"ADJUNTO: este correo lleva un Excel adjunto ({nombre_adjunto}) "
        f"con el detalle de las glosas a corregir. Mencionalo explícitamente "
        f"en el cuerpo (ej: 'Adjunto Excel con el detalle de las glosas a "
        f"corregir.').\n"
        if nombre_adjunto
        else ""
    )

    bloque_extra = ""
    if contexto_extra:
        if "errores_detectados" in contexto_extra:
            errores = contexto_extra.get("errores_detectados") or []
            respuesta = (contexto_extra.get("respuesta_anterior") or "").strip()
            bloque_extra = (
                "RESPUESTA ANTERIOR DEL DESTINATARIO (citá lo relevante):\n"
                f"---\n{respuesta}\n---\n\n"
                "ERRORES DETECTADOS A MOSTRAR EN EL CORREO:\n"
                + "\n".join(f"- {e}" for e in errores)
                + "\n"
            )
        elif "persona_a_la_que_derivo" in contexto_extra:
            otro = contexto_extra.get("persona_a_la_que_derivo") or "(otra persona)"
            bloque_extra = (
                f"LA PERSONA TE DERIVÓ A: {otro}\n"
                "El correo le devuelve la responsabilidad al destinatario.\n"
            )

    return f"""\
DESTINATARIO PRINCIPAL: {destinatario_principal}
{bloque_copia}{bloque_adjunto}
INTENCIÓN: {intencion}

TRATAMIENTO: {tratamiento}
TONO: {tono}

DATOS DEL TRABAJO
- Descripción: {trabajo['descripcion']}
- Plazo: {fecha}

{bloque_extra}
Generá el cuerpo del correo. No incluyas asunto ni firma.
"""


# --------------------------------------------------------------------------
# Entrada pública
# --------------------------------------------------------------------------


def generar_correo(
    trabajo: dict[str, Any],
    *,
    tipo_correo: str = "primer_envio",
    contexto_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Devuelve dict listo para `guardar_mensaje` / `enviar_mensaje`.

    Si tipo_correo == 'primer_envio', genera Excel con glosas a corregir y
    lo deja en `adjunto_bytes` + `nombre_adjunto` para que job_diario lo
    pase a `enviar_mensaje`. Recordatorio asume que el Excel ya se mandó
    en el primer envío y no lo regenera. Aclaracion/derivado no llevan
    adjunto.
    """
    # 1. Routing determinístico (Python decide TO/CC).
    routing = _lookup_routing(tipo_correo, trabajo["zona"], trabajo["nivel_roce"])
    destinatarios_to, destinatarios_cc = _resolver_routing_a_ids(routing, trabajo)

    # 2. Datos para el LLM (descriptores en lenguaje natural).
    if routing["to"] == "jefe":
        destinatario_principal = f"jefatura del área {trabajo['area']}"
        persona_en_copia = (
            trabajo["persona"] if "persona" in routing.get("cc", []) else None
        )
    else:
        destinatario_principal = trabajo["persona"]
        persona_en_copia = None

    intencion = INTENCION_POR_TIPO[tipo_correo]
    tratamiento = TRATAMIENTO_POR_ROCE.get(
        trabajo.get("nivel_roce") or "",
        "balanceado, formal pero cercano",
    )
    tono = URGENCIA_POR_ZONA.get(trabajo["zona"], "tono cordial estándar")

    # 3. Adjunto (solo en primer_envio).
    adjunto_bytes: bytes | None = None
    nombre_adjunto: str | None = None
    if tipo_correo == "primer_envio":
        adjunto_bytes, nombre_adjunto = generar_excel_adjunto(trabajo)

    # 4. LLM redacta el cuerpo.
    chat = ChatOpenAI(model=MODEL, temperature=TEMPERATURA)
    resp = chat.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=_user_prompt(
                    trabajo=trabajo,
                    destinatario_principal=destinatario_principal,
                    persona_en_copia=persona_en_copia,
                    intencion=intencion,
                    tratamiento=tratamiento,
                    tono=tono,
                    contexto_extra=contexto_extra,
                    nombre_adjunto=nombre_adjunto,
                )
            ),
        ]
    )
    contenido = resp.content.strip()

    # 5. Asunto determinístico.
    asunto = _calcular_asunto(tipo_correo, trabajo)

    return {
        "trabajo_id": trabajo["trabajo_id"],
        "remitente_id": AGENTE_PERSONA_ID,
        "destinatarios_to": destinatarios_to,
        "destinatarios_cc": destinatarios_cc,
        "asunto": asunto,
        "contenido": contenido,
        "zona": trabajo["zona"],
        "tipo_correo": tipo_correo,
        "adjunto_bytes": adjunto_bytes,
        "nombre_adjunto": nombre_adjunto,
    }
