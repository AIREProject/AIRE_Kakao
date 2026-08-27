import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BACKEND_URL = os.getenv("BACKEND_URL", "https://traip.mtvs2026.work").rstrip("/")
KAKAO_ADAPTER_TOKEN = os.getenv("KAKAO_ADAPTER_TOKEN", "")
SAVE_SLOT_ID = os.getenv("SAVE_SLOT_ID", "demo-slot-1")
COMPANION_ID = os.getenv("COMPANION_ID", "mako")
KAKAO_SKILL_SECRET = os.getenv("KAKAO_SKILL_SECRET", "")
API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "35"))
PORT = int(os.getenv("PORT", "10000"))
