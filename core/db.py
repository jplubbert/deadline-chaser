import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def get_connection() -> psycopg.Connection:
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError(
            f"POSTGRES_PASSWORD vacío. Edita {_ENV_PATH} y reintenta."
        )
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "postgres"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=password,
    )
