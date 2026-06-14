"""agent-hub 전역 설정. .env를 읽어 모든 모듈이 공유하는 단일 소스."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# --- 경로 ---
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
DB_PATH = DATA_DIR / "hermes.db"
CHROMA_PATH = DATA_DIR / "chroma"
VAULT_PATH = Path(os.getenv("VAULT_PATH", str(ROOT / "vault"))).resolve()

# --- Ollama (로컬 무료 워커) ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# --- 쇼츠 파이프라인 ---
SHORTS_DIR = DATA_DIR / "shorts"
STOCK_DIR = DATA_DIR / "stock"  # Pexels 등 다운로드 영상 캐시
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "ko-KR-InJoonNeural")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")  # 무료 스톡영상 배경(https://www.pexels.com/api/)

# --- Discord ---
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID") or 0)
DISCORD_APPROVAL_CHANNEL_ID = int(os.getenv("DISCORD_APPROVAL_CHANNEL_ID") or 0)
DISCORD_LOG_CHANNEL_ID = int(os.getenv("DISCORD_LOG_CHANNEL_ID") or 0)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# --- 트렌드 수집 ---
TREND_RSS_FEEDS: list[str] = [
    u.strip() for u in os.getenv("TREND_RSS_FEEDS", "").split(",") if u.strip()
]
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

DATA_DIR.mkdir(parents=True, exist_ok=True)
