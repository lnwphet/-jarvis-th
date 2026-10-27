import argparse
import os

from flask import Flask, jsonify, render_template, request

from brain import make_brain
from main import MAX_STEPS, SYSTEM_PROMPT
from tools import run_tool

app = Flask(__name__)
brain = make_brain()
conversation = [{"role": "system", "content": SYSTEM_PROMPT}]


@app.get("/")
def index():
    return render_template("index.html", model=brain.name)


@app.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("message", "")).strip()
    if not text:
        return jsonify({"error": "ข้อความว่าง"}), 400

    working = conversation + [{"role": "user", "content": text}]
    try:
        reply, tools_used = _run_turn(working)
    except RuntimeError as exc:
        return jsonify({"reply": f"เกิดปัญหากับสมอง AI — {exc}", "tools": [], "error": True})

    conversation[:] = working
    return jsonify({"reply": reply, "tools": tools_used})


@app.post("/reset")
def reset():
    conversation[:] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return jsonify({"ok": True})


def _run_turn(working: list[dict]) -> tuple[str, list[str]]:
    tools_used: list[str] = []
    for _ in range(MAX_STEPS):
        result = brain.reply(working)
        working.append(result["assistant"])
        if not result["tool_calls"]:
            return result["assistant"].get("content") or "(ไม่มีคำตอบ)", tools_used
        for call in result["tool_calls"]:
            tools_used.append(call["name"])
            output = run_tool(call["name"], call["arguments"])
            working.append(
                {"role": "tool", "tool_call_id": call["id"], "content": output}
            )
    return "ผมทำงานหลายขั้นเกินไปแล้ว ลองสั่งให้เล็กลงหน่อยครับ", tools_used


def main() -> None:
    parser = argparse.ArgumentParser(description="จาร์วิส เว็บแอพ")
    parser.add_argument("--lan", action="store_true", help="เปิดให้มือถือใน Wi-Fi เดียวกันเข้าได้")
    args = parser.parse_args()

    port = int(os.environ.get("PORT", "5000"))
    host = "0.0.0.0" if (args.lan or "PORT" in os.environ) else "127.0.0.1"

    print("=" * 52)
    print(f"  จาร์วิส เว็บ — สมอง: {brain.name}")
    print(f"  เปิดเบราว์เซอร์ไปที่ http://localhost:{port}")
    if host == "0.0.0.0":
        print("  โหมด LAN: มือถือในบ้านเปิด http://<IP ของคอม>:<port>")
    print("  กด Ctrl+C เพื่อหยุด")
    print("=" * 52)
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
