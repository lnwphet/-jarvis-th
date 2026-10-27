import json
import os
import time
from pathlib import Path
from urllib import error, request

from tools import TOOL_SCHEMAS

BASE_DIR = Path(__file__).parent
MAX_ATTEMPTS = 3
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
REQUEST_TIMEOUT = 60


class _TransientAPIError(Exception):
    """ข้อผิดพลาดชั่วคราว (โมเดลไม่ว่าง เน็ตสะดุด) ลองใหม่ได้"""


class MockBrain:
    """สมองจำลองที่ตอบตามคำสำคัญ ทำงานได้โดยไม่ต้องมี API key เพื่อให้เห็น flow ทั้งระบบ"""

    name = "mock"

    def reply(self, messages: list[dict]) -> dict:
        last = messages[-1]
        if last["role"] == "tool":
            return _text(f"ผลลัพธ์: {last['content']}")

        text = last["content"].strip()
        low = text.lower()

        if any(
            key in low
            for key in ("กี่โมง", "เวลาเท่าไร", "เวลาเท่าไหร่", "วันที่เท่าไร", "วันที่เท่าไหร่", "what time", "today")
        ):
            return _call("get_current_time", {})
        if low.startswith(("จด ", "บันทึก ", "note ")):
            return _call("add_note", {"text": _after(text, "จด ", "บันทึก ", "note ")})
        if any(key in low for key in ("โน้ต", "notes", "ที่จดไว้")):
            return _call("list_notes", {})
        if low.startswith(("ค้นหา", "search ", "คืออะไร", "รู้จัก")):
            return _call(
                "search_wikipedia",
                {"query": _after(text, "ค้นหา", "search ", "คืออะไร", "รู้จัก")},
            )
        if any(key in low for key in ("สวัสดี", "hello", "สวัสดีครับ", "หวัดดี")):
            return _text(
                "สวัสดีครับ ผมจาร์วิส (โหมดทดลอง ไม่ใช้ AI จริง)\n"
                "ลองสั่งผมดู: 'กี่โมงแล้ว' / 'จด ซื้อนม' / 'โน้ต' / 'ค้นหา ปารีส'"
            )

        return _text(
            "ตอนนี้ผมอยู่โหมดทดลอง จึงเข้าใจแค่คำสั่งตัวอย่าง:\n"
            "  - กี่โมงแล้ว\n"
            "  - จด <ข้อความ>\n"
            "  - โน้ต\n"
            "  - ค้นหา <หัวข้อ>\n"
            "ถ้าอยากให้ผมตอบได้ทุกคำถาม: เปิดไฟล์ .env แล้ววาง API key ต่อท้าย OPENAI_API_KEY="
        )


class OpenAIBrain:
    """สมองตัวจริง ใช้ API แบบ OpenAI (ใช้ได้กับ OpenRouter, Groq, Ollama ด้วย)"""

    name = "openai"

    def __init__(self, api_key: str, base_url: str, model: str, fallback_model: str = ""):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.fallback_model = fallback_model
        self.name = model

    def reply(self, messages: list[dict]) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                data = self._post(messages)
                break
            except _TransientAPIError as exc:
                last_error = exc
                if attempt < MAX_ATTEMPTS:
                    delay = attempt * 5
                    print(f"  [ระบบ] {exc} — รอ {delay} วินาทีแล้วลองใหม่ ({attempt + 1}/{MAX_ATTEMPTS})")
                    time.sleep(delay)
        else:
            raise RuntimeError(f"ลอง {MAX_ATTEMPTS} ครั้งแล้วยังไม่สำเร็จ: {last_error}") from last_error

        message = data["choices"][0]["message"]
        tool_calls = [
            {
                "id": call["id"],
                "name": call["function"]["name"],
                "arguments": _parse_arguments(call["function"].get("arguments")),
            }
            for call in message.get("tool_calls") or []
        ]
        return {"assistant": message, "tool_calls": tool_calls}

    def _post(self, messages: list[dict]) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "tool_choice": "auto",
        }
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.load(resp)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            if exc.code in RETRY_STATUSES:
                if exc.code == 429 and self.fallback_model and self.model != self.fallback_model:
                    print(f"  [ระบบ] โควตาของ {self.model} หมดแล้ว สลับไปใช้ {self.fallback_model}")
                    self.model = self.fallback_model
                    self.name = self.fallback_model
                    raise _TransientAPIError("สลับโมเดลสำรองแล้ว") from exc
                reason = "ถึงโควตาการใช้งานฟรี (429)" if exc.code == 429 else f"เซิร์ฟเวอร์ไม่พร้อม ({exc.code})"
                raise _TransientAPIError(reason) from exc
            raise RuntimeError(f"API ตอบกลับ {exc.code}: {detail}") from exc
        except OSError as exc:
            raise _TransientAPIError(f"การเชื่อมต่อสะดุด: {type(exc).__name__}") from exc


def make_brain() -> MockBrain | OpenAIBrain:
    _load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return MockBrain()
    return OpenAIBrain(
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        fallback_model=os.environ.get("OPENAI_FALLBACK_MODEL", "").strip(),
    )


def _text(content: str) -> dict:
    return {"assistant": {"role": "assistant", "content": content}, "tool_calls": []}


def _call(name: str, arguments: dict, content: str | None = None) -> dict:
    raw_arguments = json.dumps(arguments, ensure_ascii=False)
    return {
        "assistant": {
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": f"mock-{name}",
                    "type": "function",
                    "function": {"name": name, "arguments": raw_arguments},
                }
            ],
        },
        "tool_calls": [{"id": f"mock-{name}", "name": name, "arguments": arguments}],
    }


def _after(text: str, *triggers: str) -> str:
    low = text.lower()
    for trigger in triggers:
        index = low.find(trigger)
        if index >= 0:
            return text[index + len(trigger):].strip(" :?؟")
    return text.strip()


def _parse_arguments(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
