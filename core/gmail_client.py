"""Cliente Gmail con OAuth para enviar y leer correo en nombre del usuario."""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = _PROJECT_ROOT / "credentials.json"
TOKEN_PATH = _PROJECT_ROOT / "token.json"


def get_gmail_service():
    """Devuelve el servicio Gmail autenticado.

    Si `token.json` existe y es válido, reutiliza esas credenciales.
    Si está vencido pero hay refresh_token, lo refresca silenciosamente.
    Si no, abre el flow OAuth en el navegador y persiste el token resultante.
    """
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds is None or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Falta {CREDENTIALS_PATH}. Bajalo desde GCP "
                    f"(OAuth client de tipo Desktop)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)
