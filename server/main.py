# server/main.py
import json
import os
import uuid
from datetime import datetime

from fastapi import FastAPI, Response, Body, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from openai import OpenAI  # Ollama'yı OpenAI-uyumlu API ile çağıracağız

# --- DB (SQLModel / SQLite) ---
from sqlmodel import SQLModel, Field, create_engine, Session, select

from core.settings import (
    ALLOWED_ORIGINS,
    # Ollama ayarları (.env'den geliyor)
    OLLAMA_BASE_URL, OLLAMA_MODEL,
)
from core.schemas import ChatPayload, Msg, PlanRequest, PlanResult
from agents.planner import build_plan_prompt, extract_json, normalize_args
from tools import dispatch

# (Google OAuth uçları aynı kalsın)
from server.google_oauth import start_auth_url, exchange_code_save_token

# =============================================================================
# DB MODELLERİ ve BAŞLATMA
# =============================================================================

engine = create_engine("sqlite:///./.data/agentic.db", connect_args={"check_same_thread": False})

class Conversation(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Message(SQLModel, table=True):
    id: str = Field(primary_key=True)
    conv_id: str = Field(index=True, foreign_key="conversation.id")
    role: str                     # "user" | "assistant" | "tool"
    content: str
    tool_output: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

def init_db():
    os.makedirs(".data", exist_ok=True)
    SQLModel.metadata.create_all(engine)

# =============================================================================
# APP
# =============================================================================

app = FastAPI(
    title="Agentic Assistant (Local Ollama)",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

@app.on_event("startup")
def _startup():
    init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- LLM Client (Ollama / OpenAI-uyumlu) ----
oai = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")  # api_key dummy
ACTIVE_MODEL = OLLAMA_MODEL
print(f"[BOOT] LLM=Ollama model={ACTIVE_MODEL} base={OLLAMA_BASE_URL}")

SYSTEM_PREFIX = "You are a helpful, concise assistant. Reply in Turkish if the user speaks Turkish."

def build_prompt(msgs: list[Msg]) -> str:
    sys = [m.content for m in msgs if m.role == "system"]
    sys_text = sys[-1] if sys else SYSTEM_PREFIX
    lines = []
    for m in msgs:
        if m.role == "system":
            continue
        who = "User" if m.role == "user" else "Assistant"
        lines.append(f"{who}: {m.content}")
    lines.append("Assistant:")
    return sys_text + "\n\n" + "\n".join(lines)

# ---- LLM helpers (chat-only) ----
def llm_once(prompt: str, *, max_new_tokens=512, temperature=0.2) -> str:
    r = oai.chat.completions.create(
        model=ACTIVE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_new_tokens,
    )
    return r.choices[0].message.content

def llm_stream(prompt: str, *, max_new_tokens=512, temperature=0.2):
    stream = oai.chat.completions.create(
        model=ACTIVE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_new_tokens,
        stream=True,
    )
    for chunk in stream:
        piece = (chunk.choices[0].delta.content or "")
        if piece:
            yield piece

# =============================================================================
# ROOT & HEALTH
# =============================================================================

@app.get("/")
def index():
    return {
        "ok": True,
        "service": "Agentic Assistant (Local Ollama)",
        "model": ACTIVE_MODEL,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }

@app.get("/health")
def health():
    return {"ok": True, "model": ACTIVE_MODEL}

# =============================================================================
# GOOGLE OAUTH
# =============================================================================

@app.get("/auth/google/start")
def google_auth_start():
    url = start_auth_url()
    return {"auth_url": url}

@app.get("/auth/google/callback")
def google_auth_callback(code: str, state: str | None = None):
    try:
        exchange_code_save_token(code)
        return {"ok": True, "msg": "Google auth completed. Token saved."}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

# =============================================================================
# FAVICON STUBS
# =============================================================================

@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)

@app.get("/apple-touch-icon.png")
def apple_touch_icon():
    return Response(status_code=204)

@app.get("/apple-touch-icon-precomposed.png")
def apple_touch_icon_precomposed():
    return Response(status_code=204)

# =============================================================================
# CHAT (SSE) & SINGLE SHOT
# =============================================================================

@app.post("/chat")
def chat(payload: ChatPayload):
    prompt = build_prompt(payload.messages)

    def token_stream():
        try:
            for piece in llm_stream(
                prompt,
                max_new_tokens=payload.max_new_tokens or 512,
                temperature=payload.temperature or 0.2,
            ):
                yield f"data:{json.dumps({'token': piece})}\n\n"
        except Exception as e:
            yield f"data:{json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(token_stream(), media_type="text/event-stream")

@app.post("/chat_once")
def chat_once(payload: ChatPayload = Body(...)):
    prompt = build_prompt(payload.messages)
    try:
        text = llm_once(
            prompt,
            max_new_tokens=payload.max_new_tokens or 512,
            temperature=payload.temperature or 0.2,
        )
        return {"text": text}
    except Exception as e:
        return JSONResponse({"error": f"{e}"}, status_code=502)

# =============================================================================
# CONVERSATION CRUD (SQLite)
# =============================================================================

@app.post("/conversations")
def create_conv(title: str = "Yeni sohbet"):
    cid = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(Conversation(id=cid, title=title))
        s.commit()
    return {"id": cid, "title": title}

@app.get("/conversations")
def list_convs():
    with Session(engine) as s:
        rows = s.exec(select(Conversation).order_by(Conversation.updated_at.desc())).all()
        return [{"id": c.id, "title": c.title, "updated_at": c.updated_at} for c in rows]

@app.get("/conversations/{cid}")
def get_conv(cid: str):
    with Session(engine) as s:
        conv = s.get(Conversation, cid)
        if not conv:
            raise HTTPException(404, "conversation not found")
        msgs = s.exec(
            select(Message).where(Message.conv_id == cid).order_by(Message.created_at)
        ).all()
        out = []
        for m in msgs:
            out.append({
                "role": m.role,
                "content": m.content,
                "tool_output": json.loads(m.tool_output) if m.tool_output else None,
                "created_at": m.created_at,
            })
        return {"id": cid, "title": conv.title, "messages": out}

@app.delete("/conversations/{cid}")
def delete_conv(cid: str):
    with Session(engine) as s:
        # mesajları sil
        msgs = s.exec(select(Message).where(Message.conv_id == cid)).all()
        for m in msgs:
            s.delete(m)
        conv = s.get(Conversation, cid)
        if conv:
            s.delete(conv)
        s.commit()
    return {"ok": True}

# =============================================================================
# PLANNER + TOOL-CALLING  (DB'ye yazan versiyon)
# =============================================================================

def _get_or_create_conversation(title_hint: str | None, cid_header: str | None) -> str:
    """Header ile gelen conversation id varsa doğrula, yoksa yeni oluştur."""
    with Session(engine) as s:
        if cid_header:
            c = s.get(Conversation, cid_header)
            if c:
                return c.id
        # yeni oluştur
        cid = str(uuid.uuid4())
        s.add(Conversation(id=cid, title=(title_hint or "Yeni sohbet")[:80]))
        s.commit()
        return cid

def _save_messages(cid: str, user_text: str, final_answer: str, tool_output: dict | None):
    with Session(engine) as s:
        s.add(Message(
            id=str(uuid.uuid4()),
            conv_id=cid, role="user", content=user_text
        ))
        s.add(Message(
            id=str(uuid.uuid4()),
            conv_id=cid, role="assistant",
            content=final_answer,
            tool_output=json.dumps(tool_output, ensure_ascii=False) if tool_output else None
        ))
        conv = s.get(Conversation, cid)
        if conv:
            if conv.title.strip().lower() in {"yeni sohbet", ""}:
                conv.title = (user_text or conv.title)[:80]
            conv.updated_at = datetime.utcnow()
            s.add(conv)
        s.commit()

@app.post("/plan")
def plan(req: PlanRequest, request: Request):
    # 1) Plan üret (2 deneme)
    try:
        plan_prompt = build_plan_prompt(req.user_input)
        plan_text = llm_once(plan_prompt, max_new_tokens=220, temperature=0.1)
        obj = extract_json(plan_text)
        if not obj:
            harder = plan_prompt + "\nOutput must be ONLY one JSON object. No explanations."
            plan_text = llm_once(harder, max_new_tokens=200, temperature=0.0)
            obj = extract_json(plan_text)
    except Exception as e:
        return JSONResponse({"error": f"LLM plan call failed: {e}"}, status_code=502)

    # 1c) Heuristik fallback
    if not obj:
        text = req.user_input.lower()
        if any(w in text for w in ["yarın", "hafta", "öğleden sonra", "takvim", "randevu", "blok"]):
            obj = {
                "tool": "calendar",
                "args": {"start_iso": "2025-08-20T13:00", "end_iso": "2025-08-27T18:00", "block_hours": 2},
                "reason": "Heuristic fallback from Turkish request.",
            }
        else:
            obj = {"tool": "none", "args": {}, "reason": "Heuristic fallback: no tool."}

    tool = obj.get("tool", "none")
    args = normalize_args(obj.get("args", {}) or {})

    # 2) Tool'u çağır
    tool_output = None
    try:
        if tool in {"calendar", "gmail", "tasks"}:
            tool_output = dispatch(tool, args)
    except Exception as e:
        tool_output = {"error": str(e)}

    # 3) Final yanıt (TR, maddeli)
    msgs = [
        Msg(role="system", content="Kısa ve eyleme dönük Türkçe yanıt ver. Maddeli yaz."),
        Msg(role="user", content=f"Kullanıcı isteği: {req.user_input}"),
    ]
    if tool_output:
        msgs.append(Msg(role="user", content=f"Araç çıktısı (JSON): {json.dumps(tool_output, ensure_ascii=False)}"))
    prompt = build_prompt(msgs)

    try:
        final_text = llm_once(prompt, max_new_tokens=800, temperature=0.3)
    except Exception as e:
        return JSONResponse({"error": f"LLM final call failed: {e}"}, status_code=502)

    # 4) Konuşmayı belirle / oluştur ve DB'ye yaz
    cid_header = request.headers.get("X-Conversation-Id")
    conversation_id = _get_or_create_conversation(req.user_input, cid_header)
    _save_messages(conversation_id, req.user_input, final_text.strip(), tool_output)

    return {
        "conversation_id": conversation_id,
        "plan_text": plan_text,
        "tool_call": {"tool": tool, "args": args, "reason": obj.get("reason")},
        "tool_output": tool_output,
        "final_answer": final_text.strip(),
    }