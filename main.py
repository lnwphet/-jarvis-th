import json
import sys

from brain import make_brain
from tools import run_tool

MAX_STEPS = 5
EXIT_WORDS = {"quit", "exit", "ออก", "บาย"}

SYSTEM_PROMPT = """คุณคือจาร์วิส ผู้ช่วยส่วนตัวที่พูดภาษาไทย ตอบสั้น ตรงประเด็น
ใช้ tool เมื่อจำเป็นต้องรู้ข้อมูลจริง ห้ามเดาเวลาหรือข้อเท็จจริงเอง
ถ้าไม่แน่ใจหรือข้อมูลไม่พอ ให้บอกผู้ใช้ตรง ๆ
ก่อนทำอะไรที่ย้อนกลับไม่ได้หรือมีผลข้างเคียง ถามยืนยันผู้ใช้ก่อน"""


def main() -> None:
    _force_utf8()
    brain = make_brain()

    print("=" * 54)
    print("  จาร์วิส เวอร์ชัน 0.1")
    print(f"  สมอง: {brain.name}" + (" (AQ.Ab8RN6JnqYwECq33xgzYDMoQBVqAl2wzfRGoVf6ZQD1v4qrvcg)" if brain.name == "mock" else ""))
    print("  พิมพ์ 'ออก' เพื่อเลิก")
    print("=" * 54)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("\nคุณ: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nจาร์วิส: แล้วพบกันใหม่ครับ")
            return
        if not user_input:
            continue
        if user_input.lower() in EXIT_WORDS:
            print("จาร์วิส: แล้วพบกันใหม่ครับ")
            return

        messages.append({"role": "user", "content": user_input})

        for _ in range(MAX_STEPS):
            try:
                result = brain.reply(messages)
            except RuntimeError as exc:
                print(f"\nจาร์วิส: เกิดปัญหากับสมอง AI — {exc}")
                messages.pop()
                break

            messages.append(result["assistant"])

            if not result["tool_calls"]:
                print(f"\nจาร์วิส: {result['assistant'].get('content') or '(ไม่มีคำตอบ)'}")
                break

            for call in result["tool_calls"]:
                print(f"  [เรียก tool] {call['name']} {json.dumps(call['arguments'], ensure_ascii=False)}")
                output = run_tool(call["name"], call["arguments"])
                print(f"  [ผลลัพธ์] {output[:300]}")
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": output}
                )
        else:
            print("\nจาร์วิส: ผมวนทำงานหลายขั้นเกินไปแล้ว ลองสั่งให้เล็กลงหน่อยครับ")


def _force_utf8() -> None:
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    main()
