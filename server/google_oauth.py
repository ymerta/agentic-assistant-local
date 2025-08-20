# server/google_oauth.py
import os
import json
from typing import Optional
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly",
          "https://www.googleapis.com/auth/calendar.events",
          "https://www.googleapis.com/auth/gmail.readonly",]

TOKEN_DIR = ".data"
TOKEN_PATH = os.path.join(TOKEN_DIR, "google_token.json")  # dev için basit dosya

def _client_config():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise RuntimeError("Missing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in environment.")
    return {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "project_id": "ai-personal-assistant",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }

def _save_creds(creds: Credentials) -> None:
    os.makedirs(TOKEN_DIR, exist_ok=True)
    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry_iso": creds.expiry.isoformat() if getattr(creds, "expiry", None) else None,
        "expiry_ts": creds.expiry.timestamp() if getattr(creds, "expiry", None) else None,
    }
    with open(TOKEN_PATH, "w") as f:
        json.dump(payload, f)

def start_auth_url(state: str = "dev") -> str:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=GOOGLE_REDIRECT_URI)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    return auth_url

def exchange_code_save_token(code: str) -> None:
    """
    Callback'te gelen 'code' ile access+refresh token alır ve kaydeder.
    """
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=GOOGLE_REDIRECT_URI)
    flow.fetch_token(code=code)
    _save_creds(flow.credentials)

def load_creds() -> Optional[Credentials]:
    """
    Kaydedilmiş kimlik bilgilerini yükler.
    - Geçersiz/expired ise ve refresh_token varsa: OTOMATİK YENİLER ve tekrar kaydeder.
    - Hiç token yoksa: None döner (UI'da /auth/google/start'a yönlendir).
    """
    if not os.path.exists(TOKEN_PATH):
        return None

    with open(TOKEN_PATH) as f:
        data = json.load(f)

    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes"),
    )

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(GoogleRequest())
                _save_creds(creds)
            except Exception as e:
                return None
        else:
            return None

    return creds