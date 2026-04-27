"""Envía los últimos 3 mensajes de la DB vía Gmail (dry-run si env lo activa)."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from psycopg.rows import dict_row

from core.db import get_connection
from core.enviar import enviar_mensaje, obtener_headers


def _ultimos_mensajes(n: int = 3) -> list[dict]:
    sql = """
        SELECT  mensaje_id, trabajo_id, remitente_id,
                destinatarios_to, destinatarios_cc,
                asunto, contenido
        FROM    mensajes
        ORDER BY mensaje_id DESC
        LIMIT   %s
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, (n,))
        return list(reversed(cur.fetchall()))


def main() -> None:
    mensajes = _ultimos_mensajes(3)
    print(f"Enviando {len(mensajes)} mensajes...\n")

    for m in mensajes:
        result = enviar_mensaje(m)
        headers = obtener_headers(
            result["gmail_message_id"], "From", "To", "Cc", "Reply-To", "Subject"
        )

        print("=" * 78)
        print(
            f"  mensaje_id={m['mensaje_id']}  trabajo_id={m['trabajo_id']}  "
            f"{'(DRY-RUN)' if result['dry_run'] else '(REAL)'}"
        )
        print(f"  gmail_message_id: {result['gmail_message_id']}")
        print()
        print("  -- Headers tal como Gmail los registró --")
        for h in ("From", "To", "Cc", "Reply-To", "Subject"):
            if h in headers:
                print(f"  {h:<10} {headers[h]}")
        print()


if __name__ == "__main__":
    main()
