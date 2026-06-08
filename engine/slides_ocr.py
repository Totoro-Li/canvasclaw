"""Per-lecture slide OCR via the vision endpoint. For each keyframe extract
{title, text}; then enrich that lecture's units (real titles + slide chunks).

    python -m engine.slides_ocr <lecture_id>          # OCR slides
    python -m engine.slides_ocr <lecture_id> enrich   # fold titles+slide text into units.json
Needs an OPENAI vision endpoint (config/.env).
"""
from __future__ import annotations
import json, re, sys
from concurrent.futures import ThreadPoolExecutor
from config.config import settings
from engine import llm

PROMPT = ("这是一张课程幻灯片。请提取其内容，严格按 JSON 返回："
          '{"title":"幻灯片标题","text":"主要文字要点；公式用文字或LaTeX描述；图表给出简要说明"}。'
          "只返回 JSON。")


def _to_str(v) -> str:
    """Vision models may return title/text as a list (bullets) or dict — coerce safely."""
    if v is None:
        return ""
    if isinstance(v, list):
        return "\n".join(_to_str(x) for x in v)
    if isinstance(v, dict):
        return "；".join(f"{k}:{_to_str(val)}" for k, val in v.items())
    return str(v)


def _ocr_one(slide: dict) -> dict:
    title, text = "", ""
    try:
        raw = llm.vision_describe(slide["frame"], PROMPT)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        obj = json.loads(m.group(0)) if m else {"title": "", "text": raw}
        title = _to_str(obj.get("title")).strip()
        text = _to_str(obj.get("text")).strip()
    except Exception as e:                           # noqa: BLE001
        text = f"(ocr error: {e})"
    return {"slide_index": slide["slide_index"], "ts": slide["ts"],
            "start_sec": slide["start_sec"], "end_sec": slide["end_sec"],
            "title": title, "ocr_text": text}


def ocr_slides(lecture_id: str, workers: int = 8) -> dict:
    slides = json.loads(settings.lec_slides_json(lecture_id).read_text(encoding="utf-8"))["slides"]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = sorted(ex.map(_ocr_one, slides), key=lambda s: s["slide_index"])
    settings.lec_slides_ocr(lecture_id).write_text(
        json.dumps({"n": len(results), "slides": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ocr:{lecture_id}] {len(results)} slides -> {settings.lec_slides_ocr(lecture_id)}")
    return {"slides": results}


def enrich_units(lecture_id: str) -> dict:
    lu = json.loads(settings.lec_units(lecture_id).read_text(encoding="utf-8"))
    ocr = {s["slide_index"]: s for s in
           json.loads(settings.lec_slides_ocr(lecture_id).read_text(encoding="utf-8"))["slides"]}
    chunks = lu["chunks"]
    for u in lu["units"]:
        titles = [ocr[i]["title"] for i in u["slide_indices"] if i in ocr and ocr[i]["title"]]
        if titles:
            u["title"] = f"{u['unit_id']} · {titles[0][:30]}"
        txts, seen = [], set()
        for i in u["slide_indices"]:
            t = ocr.get(i, {}).get("ocr_text", "")
            if t and t not in seen:
                seen.add(t); txts.append(f"[slide {i}] {t}")
        if txts:
            cid = f"{u['unit_id']}-slide"
            chunks.append({"chunk_id": cid, "unit_id": u["unit_id"], "lecture_id": lecture_id,
                           "text": "\n".join(txts), "start_sec": u["start_sec"], "end_sec": u["end_sec"],
                           "ts": u["ts"], "slide_indices": u["slide_indices"], "source": "slide",
                           "is_question": False})
            u["chunk_ids"].append(cid)
    lu["n_chunks"] = len(chunks)
    settings.lec_units(lecture_id).write_text(json.dumps(lu, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ocr:{lecture_id}] enriched titles + slide chunks -> {settings.lec_units(lecture_id)}")
    return lu


if __name__ == "__main__":
    lid = sys.argv[1] if len(sys.argv) > 1 else "L01"
    if len(sys.argv) > 2 and sys.argv[2] == "enrich":
        enrich_units(lid)
    else:
        ocr_slides(lid)
