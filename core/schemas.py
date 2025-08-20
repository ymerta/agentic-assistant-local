from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime

class TimeRange(BaseModel):
    start: datetime
    end: datetime

class CalendarEvent(BaseModel):
    id: str
    title: str
    start: datetime
    end: datetime
    location: Optional[str] = None

class MailItem(BaseModel):
    id: str
    from_name: str
    subject: str
    received_at: datetime
    snippet: str
    important: bool = False

class TaskItem(BaseModel):
    id: str
    title: str
    due: Optional[datetime] = None
    project: Optional[str] = None

# chat payload
class Msg(BaseModel):
    role: Literal["system","user","assistant"]
    content: str

class ChatPayload(BaseModel):
    messages: List[Msg]
    temperature: float | None = 0.2
    max_new_tokens: int | None = 512
    
class PlanRequest(BaseModel):
    user_input: str

class ToolCall(BaseModel):
    tool: Literal["calendar","gmail","tasks","none"]
    args: dict
    reason: str | None = None

class PlanResult(BaseModel):
    plan_text: str
    tool_call: ToolCall
    tool_output: dict | list | str | None = None
    final_answer: str | None = None