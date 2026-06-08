"""LLM access layer.

- chat / chat_json / chat_stream  -> any OpenAI-compatible endpoint (DeepSeek/OpenRouter/...)
- vision_describe                 -> multimodal endpoint (slide OCR / formula pages)
- embed                           -> LOCAL bge embeddings on GPU (no external call)

Everything funnels through here so the rest of the engine is provider-agnostic.
"""
from __future__ import annotations
import base64, json, re, time
from functools import lru_cache
from typing import List, Dict, Any, Iterator, Optional
from config.config import settings


# ---------------- OpenAI-compatible chat ----------------
@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI
    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            "No LLM credentials. Put OPENAI_BASE_URL / OPENAI_API_KEY / LLM_MODEL "
            "in canvasclaw/config/.env (see .env.example)."
        )
    return OpenAI(base_url=settings.OPENAI_BASE_URL, api_key=settings.OPENAI_API_KEY,
                  timeout=settings.REQUEST_TIMEOUT)


def chat(messages: List[Dict[str, str]], *, model: Optional[str] = None,
         temperature: Optional[float] = None, max_tokens: Optional[int] = None,
         retries: int = 2) -> str:
    last = None
    for attempt in range(retries + 1):
        try:
            r = _client().chat.completions.create(
                model=model or settings.LLM_MODEL,
                messages=messages,
                temperature=settings.LLM_TEMPERATURE if temperature is None else temperature,
                max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            )
            return r.choices[0].message.content or ""
        except Exception as e:                       # noqa: BLE001
            last = e; time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"chat() failed after {retries+1} tries: {last}")


def chat_stream(messages: List[Dict[str, str]], *, model: Optional[str] = None,
                temperature: Optional[float] = None,
                max_tokens: Optional[int] = None) -> Iterator[str]:
    stream = _client().chat.completions.create(
        model=model or settings.LLM_MODEL, messages=messages,
        temperature=settings.LLM_TEMPERATURE if temperature is None else temperature,
        max_tokens=max_tokens or settings.LLM_MAX_TOKENS, stream=True,
    )
    for ev in stream:
        delta = ev.choices[0].delta.content if ev.choices else None
        if delta:
            yield delta


def chat_json(messages: List[Dict[str, str]], *, model: Optional[str] = None,
              temperature: float = 0.0) -> Any:
    """Chat that must return JSON. Tries response_format, falls back to extraction."""
    try:
        r = _client().chat.completions.create(
            model=model or settings.ROUTER_MODEL, messages=messages,
            temperature=temperature, max_tokens=settings.LLM_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        return json.loads(r.choices[0].message.content)
    except Exception:                                # fallback: parse first {...}/[...]
        txt = chat(messages, model=model or settings.ROUTER_MODEL, temperature=temperature)
        m = re.search(r"(\{.*\}|\[.*\])", txt, re.DOTALL)
        return json.loads(m.group(1)) if m else {}


# ---------------- multimodal (slide OCR / hard pages) ----------------
def vision_describe(image_path: str, prompt: str, *, model: Optional[str] = None) -> str:
    b64 = base64.b64encode(open(image_path, "rb").read()).decode()
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ],
    }]
    return chat(messages, model=model or settings.VISION_MODEL, temperature=0.0)


# ---------------- local embeddings (GPU) ----------------
@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.EMBED_MODEL, device=settings.EMBED_DEVICE)


def embed(texts: List[str], *, is_query: bool = False) -> "list":
    import numpy as np  # noqa
    # bge models benefit from a query instruction prefix
    if is_query and "bge" in settings.EMBED_MODEL.lower():
        texts = ["为这个句子生成表示以用于检索相关文章：" + t for t in texts]
    vecs = _embedder().encode(texts, normalize_embeddings=True,
                              convert_to_numpy=True, show_progress_bar=False)
    return vecs


def ready() -> bool:
    return settings.ready()
