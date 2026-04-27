"""Smoke test de la integración Gmail: lista los últimos 5 correos del INBOX."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.gmail_client import get_gmail_service


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def main() -> None:
    service = get_gmail_service()

    profile = service.users().getProfile(userId="me").execute()
    print(f"Autenticado como: {profile.get('emailAddress')}\n")

    listing = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX"], maxResults=5)
        .execute()
    )
    messages = listing.get("messages", [])

    if not messages:
        print("INBOX vacío.")
        return

    print(f"Últimos {len(messages)} correos del INBOX:\n")
    for i, ref in enumerate(messages, 1):
        full = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=ref["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            )
            .execute()
        )
        headers = full["payload"]["headers"]
        subject = _header(headers, "Subject")
        sender = _header(headers, "From")
        date = _header(headers, "Date")
        print(f"{i}. {subject or '(sin asunto)'}")
        print(f"   From: {sender}")
        print(f"   Date: {date}")
        print()


if __name__ == "__main__":
    main()
