"""Central configuration for CanvasClaw.

All runtime knobs live here and are overridable via canvasclaw/config/.env.
The LLM layer talks to ANY OpenAI-compatible endpoint (DeepSeek, OpenRouter,
a self-hosted proxy, OpenAI, ...) — set OPENAI_BASE_URL / OPENAI_API_KEY / LLM_MODEL.
"""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # canvasclaw/
DATA = ROOT / "data"


def _load_env() -> None:
    """Minimal .env loader (no python-dotenv dependency)."""
    env = ROOT / "config" / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def _b(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


class Settings:
    # ---- project paths ----
    ROOT: Path = Path(__file__).resolve().parent.parent
    DATA: Path = ROOT / "data"

    # ---- LLM endpoint (OpenAI-compatible) ----
    OPENAI_BASE_URL: str = _b("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    OPENAI_API_KEY: str = _b("OPENAI_API_KEY") or _b("DEEPSEEK_API_KEY")
    LLM_MODEL: str = _b("LLM_MODEL", "deepseek-chat")          # worker / aggregation
    ROUTER_MODEL: str = _b("ROUTER_MODEL", LLM_MODEL)          # cheap model for routing
    VISION_MODEL: str = _b("VISION_MODEL", LLM_MODEL)          # slide OCR / description
    LLM_TEMPERATURE: float = float(_b("LLM_TEMPERATURE", "0.2"))
    LLM_MAX_TOKENS: int = int(_b("LLM_MAX_TOKENS", "1500"))
    REQUEST_TIMEOUT: int = int(_b("REQUEST_TIMEOUT", "120"))

    # ---- Embeddings (local, on-GPU by default) ----
    EMBED_MODEL: str = _b("EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
    EMBED_DEVICE: str = _b("EMBED_DEVICE", "cuda")

    # ---- Data artifacts ----
    # Multi-lecture (full semester): each lecture/video lives in its own dir under
    # data/lectures/<lecture_id>/ ; data/lectures.json is the manifest of all lectures.
    LECTURES_DIR: Path = DATA / "lectures"
    MANIFEST: Path = DATA / "lectures.json"
    INDEX_DIR: Path = Path(_b("INDEX_DIR", str(DATA / "index")))   # GLOBAL index (env-overridable for ablation)

    # legacy single-lecture paths (kept for the migration helper only)
    TRANSCRIPT: Path = DATA / "transcript.json"
    SLIDES_JSON: Path = DATA / "slides" / "slides.json"
    LECTURE_UNITS: Path = DATA / "lecture_units.json"

    @classmethod
    def lec_dir(cls, lid: str) -> Path:
        return cls.LECTURES_DIR / lid

    @classmethod
    def lec_transcript(cls, lid: str) -> Path:
        return cls.LECTURES_DIR / lid / "transcript.json"

    @classmethod
    def lec_slides_json(cls, lid: str) -> Path:
        return cls.LECTURES_DIR / lid / "slides" / "slides.json"

    @classmethod
    def lec_slides_ocr(cls, lid: str) -> Path:
        return cls.LECTURES_DIR / lid / "slides" / "slides_ocr.json"

    @classmethod
    def lec_units(cls, lid: str) -> Path:
        return cls.LECTURES_DIR / lid / "units.json"

    # ---- Lecture-unit segmentation (split the single lecture into topic units) ----
    SEGMENT_MODE: str = _b("SEGMENT_MODE", "slide")       # slide | window | toc
    WINDOW_SEC: int = int(_b("WINDOW_SEC", "300"))        # for window mode

    # ---- Retrieval / RAG ----
    CHUNK_MAX_CHARS: int = int(_b("CHUNK_MAX_CHARS", "350"))   # finer chunks -> sharper retrieval
    CHUNK_OVERLAP: int = int(_b("CHUNK_OVERLAP", "1"))    # segments of overlap
    TOP_K_CHUNKS: int = int(_b("TOP_K_CHUNKS", "6"))      # per worker
    HYBRID_ALPHA: float = float(_b("HYBRID_ALPHA", "0.5"))  # vector vs BM25 blend

    # ---- Orchestrator ----
    MAX_LECTURES_FANOUT: int = int(_b("MAX_LECTURES_FANOUT", "5"))  # design: 1-5
    CANDIDATE_TOP_K: int = int(_b("CANDIDATE_TOP_K", "8"))

    # ---- Session (Feishu multi-turn) ----
    REDIS_URL: str = _b("REDIS_URL", "")                  # empty -> in-memory store
    SESSION_TTL_SEC: int = int(_b("SESSION_TTL_SEC", "1800"))
    SESSION_MAX_TURNS: int = int(_b("SESSION_MAX_TURNS", "6"))

    @classmethod
    def ready(cls) -> bool:
        return bool(cls.OPENAI_API_KEY and cls.OPENAI_BASE_URL and cls.LLM_MODEL)

    @classmethod
    def summary(cls) -> str:
        key = cls.OPENAI_API_KEY
        masked = (key[:4] + "…" + key[-3:]) if len(key) > 8 else ("set" if key else "MISSING")
        return (f"base_url={cls.OPENAI_BASE_URL}  model={cls.LLM_MODEL}  "
                f"vision={cls.VISION_MODEL}  key={masked}  embed={cls.EMBED_MODEL}")


settings = Settings()
