# tools/calendar_tool.py
from __future__ import annotations
from datetime import datetime, timedelta, time
from typing import List, Dict, Tuple
from zoneinfo import ZoneInfo
from typing import Optional
from googleapiclient.discovery import build
from server.google_oauth import load_creds

# İhtiyacına göre TZ'yi değiştir
LOCAL_TZ = ZoneInfo("Europe/Istanbul")

def _service():
    creds = load_creds()
    if not creds:
        raise RuntimeError("Google not authorized. Visit /auth/google/start to connect.")
    # cache_discovery=False: bazı ortamlarda discovery cache hatalarını engeller
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

def _parse_local(dt_s: str) -> datetime:
    """
    '2025-08-21T13:00' gibi naive string'i local TZ ile aware datetime'a çevirir.
    Zaten timezone'lu ise local TZ'ye dönüştürür.
    """
    # Python 3.11+ isoformat parse
    try:
        dt = datetime.fromisoformat(dt_s)
    except ValueError:
        # 'YYYY-MM-DD' verilirse saat ekle
        if "T" not in dt_s:
            dt = datetime.fromisoformat(dt_s + "T00:00:00")
        else:
            raise
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    else:
        dt = dt.astimezone(LOCAL_TZ)
    # saniyeye yuvarla (RFC3339 uyumlu)
    return dt.replace(microsecond=0)

def _rfc3339(dt: datetime) -> str:
    """TZ-aware datetime'ı RFC3339 string'e çevir."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.replace(microsecond=0).isoformat()

def _overlap(a: Tuple[datetime, datetime], b: Tuple[datetime, datetime]) -> bool:
    (a_s, a_e), (b_s, b_e) = a, b
    return a_s < b_e and b_s < a_e

def _subtract_busy(free_seg: Tuple[datetime, datetime], busy_list: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    """
    Tek bir free segmentten (start, end) tüm busy'leri çıkar ve kalan free segmentleri döndür.
    """
    segments = [free_seg]
    for b in busy_list:
        new_segments: List[Tuple[datetime, datetime]] = []
        for s, e in segments:
            if not _overlap((s, e), b):
                new_segments.append((s, e))
                continue
            b_s, b_e = b
            # solda kalan parça
            if s < b_s:
                new_segments.append((s, min(e, b_s)))
            # sağda kalan parça
            if b_e < e:
                new_segments.append((max(s, b_e), e))
        segments = [(s, e) for s, e in new_segments if s < e]
    return segments
def create_event(title: str, start_iso: str, end_iso: str, timezone: Optional[str] = None):
    """
    primary takvime basit bir etkinlik ekler.
    start_iso / end_iso: RFC3339 (timezone'lu) string olmalı.
    """
    svc = _service()
    tz = timezone or str(LOCAL_TZ)
    body = {
        "summary": title,
        "start": {"dateTime": start_iso, "timeZone": tz},
        "end":   {"dateTime": end_iso,   "timeZone": tz},
    }
    ev = svc.events().insert(calendarId="primary", body=body).execute()
    return {
        "id": ev.get("id"),
        "htmlLink": ev.get("htmlLink"),
        "status": ev.get("status"),
        "summary": ev.get("summary"),
        "start": ev.get("start", {}).get("dateTime"),
        "end": ev.get("end", {}).get("dateTime"),
    }
    
def list_free_slots(start_iso: str, end_iso: str, block_hours: int = 2):
    svc = _service()

    # 1) Zaman aralığını local TZ'de belirle ve RFC3339'a çevir
    start_dt = _parse_local(start_iso)
    end_dt = _parse_local(end_iso if "T" in end_iso else end_iso + "T23:59:59")

    body = {
        "timeMin": _rfc3339(start_dt),
        "timeMax": _rfc3339(end_dt),
        "timeZone": str(LOCAL_TZ),
        "items": [{"id": "primary"}],
    }

    fb = svc.freebusy().query(body=body).execute()

    # 2) Busy bloklarını topla ve local TZ'ye çevir
    busy_intervals: List[Tuple[datetime, datetime]] = []
    cal = fb.get("calendars", {}).get("primary", {})
    for b in cal.get("busy", []):
        b_s = datetime.fromisoformat(b["start"]).astimezone(LOCAL_TZ)
        b_e = datetime.fromisoformat(b["end"]).astimezone(LOCAL_TZ)
        busy_intervals.append((b_s.replace(microsecond=0), b_e.replace(microsecond=0)))

    # 3) Gün gün 13:00–19:00 penceresinde boşlukları üret
    results = []
    block_delta = timedelta(hours=int(block_hours))

    cur_day = start_dt.date()
    last_day = end_dt.date()

    while cur_day <= last_day:
        win_start = datetime.combine(cur_day, time(13, 0), tzinfo=LOCAL_TZ)
        win_end   = datetime.combine(cur_day, time(19, 0), tzinfo=LOCAL_TZ)

        # Global aralığa kırp
        seg_start = max(win_start, start_dt)
        seg_end   = min(win_end, end_dt)

        if seg_start < seg_end:
            # O günkü free segmentlerden busy'i çıkar
            free_segments = _subtract_busy((seg_start, seg_end), busy_intervals)

            # 4) block_hours kadar dilimle
            for fs, fe in free_segments:
                cursor = fs
                while cursor + block_delta <= fe:
                    slot_end = cursor + block_delta
                    results.append({
                        "start": _rfc3339(cursor),
                        "end": _rfc3339(slot_end),
                    })
                    # ardışık (back-to-back) bloklar; istersen 15dk kayarak ilerletmek için timedelta(minutes=15) kullan
                    cursor = slot_end

        cur_day += timedelta(days=1)

    return results