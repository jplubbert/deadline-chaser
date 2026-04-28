"""Envío de mensajes vía Gmail API con soporte de dry-run por aliases.

Modo dry-run: si la variable de entorno DRY_RUN_BASE_EMAIL está seteada,
todo destinatario real se transforma en un alias del tipo
`base+local_part@gmail.com`, el subject lleva prefijo "[DRY-RUN]" y el
body lleva un encabezado con los destinatarios originales.
"""

import base64
import os
import re
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from core.db import get_connection
from core.gmail_client import get_gmail_service

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

_TAG_OK = re.compile(r"[^a-zA-Z0-9._-]+")


def transformar_a_alias(correo_real: str, base_email: str) -> str:
    """Transforma 'yolanda@banco.cl' + 'pepe@gmail.com' → 'pepe+yolanda@gmail.com'.

    Sanitiza la parte local del correo original a `[a-zA-Z0-9._-]`,
    colapsando caracteres no permitidos a "-" y limpiando bordes.
    """
    base_local, _, base_dom = base_email.partition("@")
    local = correo_real.split("@", 1)[0]
    tag = _TAG_OK.sub("-", local).strip("-.")
    tag = re.sub(r"-{2,}", "-", tag) or "x"
    return f"{base_local}+{tag}@{base_dom}"


def _resolver_emails(persona_ids: list[int]) -> list[str]:
    if not persona_ids:
        return []
    sql = (
        "SELECT persona_id, correo FROM personas "
        "WHERE persona_id = ANY(%s)"
    )
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, (persona_ids,))
        rows = dict(cur.fetchall())
    return [rows[pid] for pid in persona_ids if pid in rows]


def _construir_mime(
    to: list[str],
    cc: list[str],
    asunto: str,
    contenido: str,
    reply_to: str | None,
    adjunto_bytes: bytes | None = None,
    nombre_adjunto: str | None = None,
) -> str:
    msg = EmailMessage()
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = asunto
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(contenido)
    if adjunto_bytes and nombre_adjunto:
        msg.add_attachment(
            adjunto_bytes,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=nombre_adjunto,
        )
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def _resolver_reply_to() -> str | None:
    """Lee REPLY_TO_ALIAS del env. Si no está, deriva de DRY_RUN_BASE_EMAIL."""
    explicit = os.environ.get("REPLY_TO_ALIAS")
    if explicit:
        return explicit
    base = os.environ.get("DRY_RUN_BASE_EMAIL")
    if base and "@" in base:
        local, _, dom = base.partition("@")
        return f"{local}+agente@{dom}"
    return None


def obtener_headers(gmail_message_id: str, *nombres: str) -> dict[str, str]:
    """Devuelve un dict {nombre: valor} con los headers pedidos del mensaje enviado."""
    service = get_gmail_service()
    msg = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=gmail_message_id,
            format="metadata",
            metadataHeaders=list(nombres) or ["From", "To", "Cc", "Reply-To", "Subject"],
        )
        .execute()
    )
    return {h["name"]: h["value"] for h in msg["payload"]["headers"]}


def _persistir_envio(
    mensaje_id: int,
    gmail_id: str,
    zona_al_enviar: str | None,
    tiene_adjunto: bool,
) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE mensajes "
            "SET gmail_message_id = %s, enviado_at = NOW(), "
            "    zona_al_enviar = %s, tiene_adjunto = %s "
            "WHERE mensaje_id = %s",
            (gmail_id, zona_al_enviar, tiene_adjunto, mensaje_id),
        )


def enviar_mensaje(
    mensaje: dict[str, Any],
    *,
    adjunto_bytes: bytes | None = None,
    nombre_adjunto: str | None = None,
) -> dict[str, Any]:
    """Envía el mensaje y devuelve {gmail_message_id, to_efectivo, cc_efectivo, dry_run}.

    `mensaje` es un dict con: mensaje_id, destinatarios_to (list[int]),
    destinatarios_cc (list[int] | None), asunto (str), contenido (str).
    Si `adjunto_bytes` y `nombre_adjunto` están seteados, se adjuntan al MIME.
    """
    to_real = _resolver_emails(mensaje["destinatarios_to"] or [])
    cc_real = _resolver_emails(mensaje.get("destinatarios_cc") or [])

    base = os.environ.get("DRY_RUN_BASE_EMAIL")
    dry_run = bool(base)
    reply_to = _resolver_reply_to()

    if dry_run:
        to_efectivo = [transformar_a_alias(c, base) for c in to_real]
        cc_efectivo = [transformar_a_alias(c, base) for c in cc_real]
        asunto = f"[DRY-RUN] {mensaje['asunto']}"
        encabezado = (
            f"ORIGINAL TO:  {', '.join(to_real) or '—'}\n"
            f"ORIGINAL CC:  {', '.join(cc_real) or '—'}\n\n"
            f"Este correo fue enviado por el Agente Deadline Chaser. "
            f"Las respuestas se redirigen a {reply_to or '(sin Reply-To)'}.\n"
            f"DRY-RUN: redirigido a aliases de {base}.\n"
            f"\n{'-' * 72}\n\n"
        )
        contenido = encabezado + mensaje["contenido"]
    else:
        to_efectivo = to_real
        cc_efectivo = cc_real
        asunto = mensaje["asunto"]
        contenido = mensaje["contenido"]

    raw = _construir_mime(
        to_efectivo, cc_efectivo, asunto, contenido, reply_to,
        adjunto_bytes=adjunto_bytes, nombre_adjunto=nombre_adjunto,
    )
    service = get_gmail_service()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    gmail_id = sent["id"]

    tiene_adjunto = bool(adjunto_bytes and nombre_adjunto)
    _persistir_envio(
        mensaje["mensaje_id"], gmail_id, mensaje.get("zona"), tiene_adjunto,
    )

    return {
        "gmail_message_id": gmail_id,
        "to_efectivo": to_efectivo,
        "cc_efectivo": cc_efectivo,
        "reply_to": reply_to,
        "dry_run": dry_run,
        "tiene_adjunto": tiene_adjunto,
    }
