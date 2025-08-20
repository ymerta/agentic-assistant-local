# server/db.py
from sqlmodel import SQLModel, Field, create_engine, Session, select
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

engine = create_engine("sqlite:///./.data/agentic.db", connect_args={"check_same_thread": False})

class Conversation(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Message(SQLModel, table=True):
    id: str = Field(primary_key=True)
    conv_id: str = Field(foreign_key="conversation.id", index=True)
    role: str
    content: str
    tool_output: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

def init_db():
    import os; os.makedirs(".data", exist_ok=True)
    SQLModel.metadata.create_all(engine)

@contextmanager
def get_session():
    with Session(engine) as s:
        yield s