#!/usr/bin/env python3
"""ASR transcription with word-level timestamps (faster-whisper large-v3, GPU).
Importable: transcribe(audio_path, out_path). Outputs segment+word timestamps and
a regex first-pass `is_question_candidate` flag (stage-1 of the 2-stage detector).
"""
import json, re, sys, time, os

QUESTION_PAT = re.compile(
    r"(？|\?|为什么|为何|怎么|怎样|如何|能不能|是不是|对不对|有没有|"
    r"大家想|想一想|思考一下|谁能|谁来|什么是|是什么|哪|呢$|吗$|"
    r"\bwhy\b|\bhow\b|\bwhat\b|\bwhich\b|\bcan you\b|\bany question)",
    re.IGNORECASE,
)

# Known faster-whisper / large-v3 Chinese hallucinations on silence/music — these
# leak in despite VAD and pollute retrieval. High-precision multi-token markers.
HALLU = ("点赞订阅", "订阅转发", "转发打赏", "打赏支持", "明镜与点点", "点点栏目",
         "明镜火点", "请不吝", "字幕组", "中文字幕", "本字幕", "字幕by", "字幕志愿",
         "谢谢观看请", "感谢观看本", "下期再见", "点个关注", "关注我的频道", "未经允许")


def _is_hallucination(text: str) -> bool:
    t = text.replace(" ", "")
    return any(h in t for h in HALLU)


def _fmt(t):
    return f"{int(t//3600):02d}:{int((t%3600)//60):02d}:{int(t%60):02d}"


def transcribe(audio: str, out: str, model_name: str = None) -> dict:
    from faster_whisper import WhisperModel
    model_name = model_name or os.environ.get("ASR_MODEL", "large-v3")
    t0 = time.time()
    try:
        model = WhisperModel(model_name, device="cuda", compute_type="float16"); dev = "cuda"
    except Exception as e:
        print(f"[asr] cuda load failed ({e}); CPU int8", flush=True)
        model = WhisperModel(model_name, device="cpu", compute_type="int8"); dev = "cpu"
    # language: auto-detect fails on some lectures (quiet/music intro -> 'nn') and bails
    # with 0 segments; this is an all-Chinese course, so allow forcing via ASR_LANG=zh.
    # condition_on_previous_text=False stops decoder-cascade derailment that otherwise
    # truncates long lectures (a bad window poisoning all subsequent ones).
    lang = os.environ.get("ASR_LANG") or None
    segments, info = model.transcribe(
        audio, language=lang, word_timestamps=True, vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500), beam_size=5,
        condition_on_previous_text=False,
        initial_prompt="以下是一节关于人工智能、智能体（Agent）、大语言模型的研究生课程录播。")
    segs, nq, n_hallu, sid = [], 0, 0, 0
    for seg in segments:
        text = seg.text.strip()
        if _is_hallucination(text):
            n_hallu += 1; continue
        is_q = bool(QUESTION_PAT.search(text)); nq += is_q
        segs.append({"id": sid, "start": round(seg.start, 2), "end": round(seg.end, 2),
                     "ts": _fmt(seg.start), "text": text, "is_question_candidate": is_q,
                     "words": [{"w": w.word, "start": round(w.start, 2), "end": round(w.end, 2)}
                               for w in (seg.words or [])]})
        sid += 1
    data = {"language": info.language, "duration_sec": round(info.duration, 1),
            "model": model_name, "device": dev, "n_segments": len(segs),
            "n_question_candidates": nq, "n_hallucinations_filtered": n_hallu, "segments": segs}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"[asr] {len(segs)} segs, {nq} q-cand, lang={info.language}, {time.time()-t0:.0f}s -> {out}", flush=True)
    return data


if __name__ == "__main__":
    transcribe(sys.argv[1] if len(sys.argv) > 1 else "data/audio.wav",
               sys.argv[2] if len(sys.argv) > 2 else "data/transcript.json")
