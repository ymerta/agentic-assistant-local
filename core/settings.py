# core/settings.py
import os
from dotenv import load_dotenv
load_dotenv()

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# LLM backend seçimi
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama")

# Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

# HF (opsiyonel)
HF_MODEL = os.getenv("HF_MODEL", "")
HF_TOKEN = os.getenv("HF_TOKEN", "")

# NEW 👇
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"