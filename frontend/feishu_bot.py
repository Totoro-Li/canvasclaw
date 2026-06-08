"""CanvasClaw — Feishu (Lark) bot frontend (the report's locked frontend).

Architecture (report §6.2): Feishu client -> event long-connection -> backend
(message handler + LangGraph engine + interactive-card builder).

Transport is the lark-cli already configured on this box:
  * inbound : `lark-cli event consume im.message.receive_v1 --as bot`  (NDJSON stream)
  * outbound: `lark-cli im +messages-reply --msg-type interactive --content <card>`

Run:  python frontend/feishu_bot.py
Multi-turn sessions keyed by chat_id (in-memory; set REDIS_URL to externalize),
SESSION_TTL_SEC idle timeout (design: 30 min).
"""
from __future__ import annotations
import sys, json, subprocess, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config.config import settings
from engine.agent import CanvasClaw

EVENT_KEY = "im.message.receive_v1"


# ---------------- sessions ----------------
class Sessions:
    def __init__(self):
        self.mem: dict[str, dict] = {}

    def history(self, chat_id: str) -> list[dict]:
        s = self.mem.get(chat_id)
        if not s or time.time() - s["t"] > settings.SESSION_TTL_SEC:
            self.mem[chat_id] = {"t": time.time(), "h": []}
        return self.mem[chat_id]["h"]

    def add(self, chat_id: str, role: str, content: str):
        h = self.history(chat_id)
        h.append({"role": role, "content": content})
        del h[: max(0, len(h) - settings.SESSION_MAX_TURNS * 2)]
        self.mem[chat_id]["t"] = time.time()


# ---------------- card builder ----------------
def build_card(res: dict) -> dict:
    elems = [{"tag": "markdown", "content": res.get("answer", "") or "（无内容）"}]
    cits, seen = res.get("citations", []), set()
    if cits:
        elems.append({"tag": "hr"})
        lines = []
        for c in cits:
            key = (c["unit_id"], c.get("ts"))
            if key in seen:
                continue
            seen.add(key)
            sl = f" · slide {c['slide_index']}" if c.get("slide_index") is not None else ""
            lt = (c.get("lecture_title") or c.get("lecture_id", ""))[:14]
            lines.append(f"📍 **[{lt}] {c['unit_id']}《{c['unit_title'][:16]}》** · ⏱ {c['ts']}{sl}")
        elems.append({"tag": "markdown", "content": "**来源讲次与时间戳**\n" + "\n".join(lines)})
    elems.append({"tag": "note", "elements": [
        {"tag": "plain_text", "content": "CanvasClaw · 多智能体课程问答 (LangGraph Orchestrator-Worker)"}]})
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue",
                   "title": {"tag": "plain_text", "content": "🎓 CanvasClaw 课程学习助手"}},
        "body": {"elements": elems},
    }


def reply_card(message_id: str, card: dict):
    subprocess.run(
        ["lark-cli", "im", "+messages-reply", "--message-id", message_id,
         "--msg-type", "interactive", "--content", json.dumps(card, ensure_ascii=False),
         "--as", "bot"],
        check=False, capture_output=True, text=True)


# ---------------- event parsing ----------------
def extract(evt: dict):
    """Return (chat_id, message_id, text, sender) from a lark IM receive event (compact or raw)."""
    e = evt.get("event", evt)
    msg = e.get("message", {})
    chat_id = msg.get("chat_id") or e.get("chat_id")
    message_id = msg.get("message_id") or e.get("message_id")
    sender = (e.get("sender", {}).get("sender_id", {}) or {}).get("open_id") or e.get("sender_id")
    content = msg.get("content") or e.get("content") or ""
    text = ""
    if isinstance(content, str):
        try:
            text = json.loads(content).get("text", "")
        except Exception:
            text = content
    elif isinstance(content, dict):
        text = content.get("text", "")
    # strip @mentions like "@_user_1 "
    import re
    text = re.sub(r"@\S+\s*", "", text).strip()
    return chat_id, message_id, text, sender


def main():
    if not settings.ready():
        sys.exit("LLM not configured — fill canvasclaw/config/.env first.")
    cc = CanvasClaw()
    sess = Sessions()
    print(f"[feishu] CanvasClaw bot up. consuming {EVENT_KEY} … ({settings.summary()})", flush=True)
    proc = subprocess.Popen(
        ["lark-cli", "event", "consume", EVENT_KEY, "--as", "bot"],
        stdout=subprocess.PIPE, text=True, bufsize=1)
    for line in proc.stdout:
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except Exception:
            continue
        chat_id, message_id, text, sender = extract(evt)
        if not (chat_id and message_id and text):
            continue
        print(f"[feishu] Q from {sender}: {text}", flush=True)
        try:
            res = cc.answer(text, sess.history(chat_id)).to_dict()
            sess.add(chat_id, "user", text)
            sess.add(chat_id, "assistant", res["answer"])
            reply_card(message_id, build_card(res))
            print(f"[feishu] replied ({len(res.get('citations', []))} citations)", flush=True)
        except Exception as e:                       # noqa: BLE001
            reply_card(message_id, {"schema": "2.0",
                "header": {"template": "red", "title": {"tag": "plain_text", "content": "CanvasClaw 出错"}},
                "body": {"elements": [{"tag": "markdown", "content": f"处理失败：{e}"}]}})


if __name__ == "__main__":
    main()
