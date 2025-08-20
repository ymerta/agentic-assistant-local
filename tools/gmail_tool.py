# tools/gmail_tool.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from server.google_oauth import load_creds


def _service():
    creds = load_creds()
    if not creds:
        raise RuntimeError("Google not authorized. Visit /auth/google/start to connect.")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _header(headers: List[Dict[str, str]], name: str) -> Optional[str]:
    name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name:
            return h.get("value")
    return None


def list_important_last_days(*, days: int = 7, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Son X günden önemli ve birincil kutudaki e-postaları getirir.
    Dönüş: [{id, threadId, subject, from, date, snippet, internal_ts}]
    """
    svc = _service()

    # Gmail arama sorgusu (promotions/social hariç, son X gün)
    q = f"newer_than:{days}d -category:promotions -category:social"

    msgs: List[Dict[str, Any]] = []
    resp = svc.users().messages().list(userId="me", q=q, maxResults=min(limit * 3, 50)).execute()
    for ref in resp.get("messages", []):
        m = svc.users().messages().get(
            userId="me",
            id=ref["id"],
            format="metadata",
            metadataHeaders=["Subject", "From", "Date"]
        ).execute()

        headers = m.get("payload", {}).get("headers", [])
        subject = _header(headers, "Subject") or "(no subject)"
        sender = _header(headers, "From") or ""
        date_hdr = _header(headers, "Date")
        snippet = (m.get("snippet") or "").strip()

        # internalDate (ms since epoch) → UTC ISO
        internal_ms = int(m.get("internalDate", "0"))
        internal_dt = datetime.fromtimestamp(internal_ms / 1000, tz=timezone.utc)

        msgs.append({
            "id": m["id"],
            "threadId": m.get("threadId"),
            "subject": subject,
            "from": sender,
            "date": date_hdr,                         # ham Date header
            "received": internal_dt.isoformat(),      # normalize edilmiş
            "snippet": snippet,
            "internal_ts": internal_ms,
        })

        if len(msgs) >= limit:
            break

    # son gelenler önce
    msgs.sort(key=lambda x: x["internal_ts"], reverse=True)
    return msgs