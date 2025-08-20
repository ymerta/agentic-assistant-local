# tools/__init__.py
from __future__ import annotations
from typing import Any, Dict

from .calendar_tool import list_free_slots, create_event
from .gmail_tool import list_important_last_days
from .tasks_tool import create_task
from .summarize_tool import summarize


def dispatch(tool: str, args: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Tek giriş noktası: aracın adını ve argümanlarını alır, uygun fonksiyonu çağırır.
    Hata durumunda akışı kesmeyip anlamlı payload döndürür.
    """
    try:
        if tool == "calendar":
            action = (args.get("action") or "").lower()

            # --- Etkinlik oluşturma ---
            if action == "create":
                title = args.get("title") or "Yeni etkinlik"
                start_iso = args.get("start_iso")
                end_iso = args.get("end_iso")
                # opsiyonel: time_zone / timezone param adı ikisini de destekleyelim
                tz = args.get("time_zone") or args.get("timezone")

                if not start_iso or not end_iso:
                    raise ValueError("Calendar create requires 'start_iso' and 'end_iso'.")

                created = create_event(title=title, start_iso=start_iso, end_iso=end_iso, timezone=tz)
                return {"created": created}

            # --- Boş saat arama ---
            start_iso = args.get("start_iso", "2025-08-20T00:00")
            end_iso = args.get("end_iso", "2025-08-27T23:59:59")
            block_hours = int(args.get("block_hours", 2))
            slots = list_free_slots(start_iso, end_iso, block_hours)

            # İsteğe bağlı: ilk N öneriyi dön (top_k)
            top_k = args.get("top_k")
            if top_k is not None:
                try:
                    k = int(top_k)
                    if k > 0:
                        slots = slots[:k]
                except Exception:
                    pass

            return {"free_slots": slots}

        if tool == "gmail":
            days = int(args.get("days", 7))
            limit = int(args.get("limit", 10))
            emails = list_important_last_days(days=days, limit=limit)
            return {"emails": emails}

        if tool == "tasks":
            title = args.get("title", "Untitled task")
            due = args.get("due")          # ISO string ya da None
            project = args.get("project")  # opsiyonel
            task = create_task(title=title, due=due, project=project)
            return {"task": task}

        # tanınmayan araç
        return {"warning": f"Unknown tool '{tool}'", "args": args}

    except Exception as e:
        return {"error": str(e), "tool": tool, "args": args}


def summarize_any(obj: Any) -> str:
    """
    Basit özetleyici yardımcı: dict/list/string tiplerine göre davranır.
    summarize_tool.summarize, liste bekliyorsa uygun forma çevirir.
    """
    if obj is None:
        return "Herhangi bir araç çıktısı yok."

    if isinstance(obj, dict):
        if "free_slots" in obj and isinstance(obj["free_slots"], list):
            items = [{"title": f"{it.get('start')} → {it.get('end')}"} for it in obj["free_slots"]]
            return summarize(items)
        if "emails" in obj and isinstance(obj["emails"], list):
            items = [{"title": em.get("subject", "(no subject)")} for em in obj["emails"]]
            return summarize(items)
        if "created" in obj and isinstance(obj["created"], dict):
            c = obj["created"]
            return f"Oluşturuldu: {c.get('summary','Etkinlik')} ({c.get('start')} → {c.get('end')})"
        if "task" in obj:
            return f"Task: {obj['task']}"
        items = [{"title": str(k)} for k in obj.keys()]
        return summarize(items)

    if isinstance(obj, list):
        items = []
        for it in obj:
            if isinstance(it, dict) and ("title" in it or "subject" in it):
                items.append({"title": it.get("title") or it.get("subject")})
            else:
                items.append({"title": str(it)})
        return summarize(items)

    return str(obj)