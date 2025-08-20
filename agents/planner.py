# agents/planner.py
import json
import re
from typing import Optional, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

# ---- Ayarlar ----
LOCAL_TZ = ZoneInfo("Europe/Istanbul")

# ---- Daha katı sistem yönergesi + few-shot örnekler ----
PLANNER_SYSTEM = """You are a strict planner.
Your ONLY job is to decide whether to call exactly one tool and with what minimal arguments.

Output rules (VERY IMPORTANT):
- Output EXACTLY ONE valid JSON object.
- No backticks, no markdown, no labels, no prefixes/suffixes, no extra text.
- Keys: "tool", "args", "reason".
- "tool" ∈ {"calendar","gmail","tasks","none"}.
- Keep "args" minimal. Use ISO 8601 for times (include minutes, seconds optional, timezone preferred).
- "reason" must be concise English and placed outside "args".
- Prefer future times (do not schedule in the past).
- If user says "yarın"/"tomorrow", resolve it as the next calendar day from today's date (context provided).
- If user gives both relative date (tomorrow) and weekday (Friday), prioritize the relative date.

Good examples:
{"tool":"calendar","args":{"start_iso":"2025-08-20T12:00","end_iso":"2025-08-27T18:00","block_hours":2},"reason":"User wants free afternoon 2-hour blocks next week."}
{"tool":"calendar","args":{"action":"create","title":"Design Review","start_iso":"2025-08-22T15:00","end_iso":"2025-08-22T17:00"},"reason":"User asked to add a meeting at a specific time."}
{"tool":"gmail","args":{"days":7,"limit":5},"reason":"User asked to summarize important emails from last week."}
{"tool":"tasks","args":{"title":"Prepare demo","due":"2025-08-22T10:00","project":"AI-Assistant"},"reason":"User wants to create a task for Friday 10am."}
{"tool":"none","args":{},"reason":"No external data needed."}
"""

PLAN_PROMPT_TEMPLATE = """{sys}

Context:
- Today (local): {today_date} ({today_weekday})
- Current time: {today_time}
- Timezone: {tz}

User request (Turkish may appear):
{user}

Return ONLY ONE JSON object on a single line as specified above. Nothing else.
"""

# ---------------- Parsers ----------------

def _strip_fences(text: str) -> str:
    """```json ... ``` veya [ASSISTANT]/[USER] kalıntılarını temizler."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = text.replace("[/ASSISTANT]", "").replace("[ASSISTANT]", "")
    text = text.replace("[/USER]", "").replace("[USER]", "")
    return text.strip()

def _find_json_span(s: str) -> Optional[str]:
    """Metin içinden son JSON objesini yakala (sağdan sola denge yöntemi)."""
    s = _strip_fences(s)
    close = s.rfind("}")
    if close == -1:
        return None
    balance = 0
    start = None
    for i in range(close, -1, -1):
        if s[i] == "}":
            balance += 1
        elif s[i] == "{":
            balance -= 1
            if balance == 0:
                start = i
                break
    if start is None:
        first = s.find("{")
        if first == -1:
            return None
        return s[first:close + 1]
    return s[start:close + 1]

def _light_sanitize(j: str) -> str:
    """JSON string’inde sık yapılan hataları toparlar."""
    j = j.strip()
    j = _strip_fences(j)
    j = j.replace("“", "\"").replace("”", "\"").replace("’", "'")
    if '"' not in j and "'" in j:
        j = j.replace("'", "\"")
    j = re.sub(r",\s*}", "}", j)
    j = re.sub(r",\s*]", "]", j)
    if j.count("{") > j.count("}"):
        j = j + "}" * (j.count("{") - j.count("}"))
    return j

def extract_json(text: str) -> Optional[dict]:
    """Model çıktısından tek JSON objesini güvenle döndürür."""
    span = _find_json_span(text)
    if not span:
        return None
    try:
        return json.loads(span)
    except Exception:
        try:
            return json.loads(_light_sanitize(span))
        except Exception:
            return None

# ---------------- Normalizer ----------------

def _ensure_tz(dt: datetime) -> datetime:
    """Naive datetime'ı local TZ ile aware yapar, microsecond=0'a yuvarlar."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    else:
        dt = dt.astimezone(LOCAL_TZ)
    return dt.replace(microsecond=0)

def _parse_iso_guess(s: str) -> Optional[datetime]:
    """Basit ISO parse; saniyesiz/naive stringleri de kabul etmeye çalışır."""
    if not s:
        return None
    try:
        # Python 3.11: fromisoformat çeşitli varyantları destekler
        dt = datetime.fromisoformat(s)
    except Exception:
        # Örn: "YYYY-MM-DDTHH:MM" veya "YYYY-MM-DD"
        if "T" in s:
            try:
                dt = datetime.fromisoformat(s + ":00")
            except Exception:
                return None
        else:
            try:
                dt = datetime.fromisoformat(s + "T00:00:00")
            except Exception:
                return None
    return _ensure_tz(dt)

def normalize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Modelden gelen args içindeki tarihleri mantıklı hâle getir:
    - due / start_iso / end_iso alanlarını ISO+TZ (Europe/Istanbul) yap.
    - Geçmiş tarihleri mümkünse bu yıla çek (ör. 2023 → 2025).
    - start > end ise düzeltmeye çalışma (çağıran katman uyarı üretir).
    """
    now = datetime.now(tz=LOCAL_TZ)

    # tasks.due
    if isinstance(args.get("due"), str):
        dt = _parse_iso_guess(args["due"])
        if dt:
            if dt.year < now.year:
                dt = dt.replace(year=now.year)
            args["due"] = dt.isoformat()

    # calendar start/end
    if isinstance(args.get("start_iso"), str):
        sdt = _parse_iso_guess(args["start_iso"])
        if sdt:
            if sdt.year < now.year:
                sdt = sdt.replace(year=now.year)
            args["start_iso"] = sdt.isoformat()

    if isinstance(args.get("end_iso"), str):
        edt = _parse_iso_guess(args["end_iso"])
        if edt:
            if edt.year < now.year:
                edt = edt.replace(year=now.year)
            args["end_iso"] = edt.isoformat()

    return args

# ---------------- Prompt builder ----------------


# ---------------- Prompt builder ----------------
def build_plan_prompt(user_input: str) -> str:
    now = datetime.now(tz=LOCAL_TZ)
    return PLAN_PROMPT_TEMPLATE.format(
        sys=PLANNER_SYSTEM,
        user=user_input,
        today_date=now.date().isoformat(),
        today_weekday=now.strftime("%A"),
        today_time=now.strftime("%H:%M"),
        tz=str(LOCAL_TZ),
    )