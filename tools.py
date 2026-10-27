import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NOTES_FILE = Path(os.environ.get("JARVIS_NOTES_FILE") or Path(__file__).parent / "notes.json")
USER_AGENT = "JarvisMVP/0.1 (learning project)"

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "คืนค่าวันที่และเวลาปัจจุบันของเครื่องผู้ใช้ ใช้เมื่อถูกถามเวลา วันที่ หรือวันในสัปดาห์",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_note",
            "description": "บันทึกข้อความสั้น ๆ ลงไฟล์โน้ตถาวรของผู้ใช้",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "เนื้อหาที่จะบันทึก"}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "อ่านรายการโน้ตที่ผู้ใช้บันทึกไว้ก่อนหน้านี้",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_wikipedia",
            "description": "ค้นข้อมูลสรุปจากวิกิพีเดีย ใช้เมื่อถูกถามข้อเท็จจริงทั่วไป เช่น บุคคล สถานที่ เหตุการณ์",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "คำค้นหา"},
                    "lang": {
                        "type": "string",
                        "description": "รหัสภาษา เช่น th หรือ en (ค่าเริ่มต้น th)",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

WEEKDAYS_TH = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]


def get_current_time() -> str:
    now = datetime.now()
    return (
        f"วัน{WEEKDAYS_TH[now.weekday()]}ที่ {now.strftime('%d/%m/%Y')} "
        f"เวลา {now.strftime('%H:%M')} น. (เวลาของเครื่องนี้)"
    )


def add_note(text: str) -> str:
    text = text.strip()
    if not text:
        return "ไม่มีข้อความให้บันทึก"
    notes = _read_notes()
    notes.append(
        {"time": datetime.now().isoformat(timespec="minutes"), "text": text}
    )
    NOTES_FILE.write_text(
        json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return f"บันทึกแล้ว: {text} (โน้ตทั้งหมด {len(notes)} รายการ)"


def list_notes(limit: int = 10) -> str:
    notes = _read_notes()
    if not notes:
        return "ยังไม่มีโน้ตที่บันทึกไว้"
    lines = [
        f"{index}. [{note.get('time', '?')}] {note.get('text', '')}"
        for index, note in enumerate(notes[-limit:], 1)
    ]
    return "โน้ตล่าสุด:\n" + "\n".join(lines)


def search_wikipedia(query: str, lang: str = "th") -> str:
    query = query.strip()
    if not query:
        return "ไม่มีคำค้นหา"
    api = f"https://{lang}.wikipedia.org/w/api.php"
    try:
        search_data = _get_json(
            api
            + "?"
            + urlencode(
                {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 1,
                    "format": "json",
                }
            )
        )
        hits = search_data.get("query", {}).get("search", [])
        if not hits:
            return f"ไม่พบข้อมูลวิกิพีเดียสำหรับ: {query}"

        title = hits[0]["title"]
        extract_data = _get_json(
            api
            + "?"
            + urlencode(
                {
                    "action": "query",
                    "prop": "extracts",
                    "exintro": 1,
                    "explaintext": 1,
                    "redirects": 1,
                    "format": "json",
                    "titles": title,
                }
            )
        )
        pages = extract_data.get("query", {}).get("pages", {})
        extract = next(iter(pages.values()), {}).get("extract", "")
        if not extract:
            return f"พบหน้า '{title}' แต่ไม่มีเนื้อหาสรุป"
        return f"วิกิพีเดีย — {title}:\n{extract[:800]}"
    except Exception as exc:
        return f"ค้นวิกิพีเดียไม่สำเร็จ (อาจเป็นปัญหาเน็ต): {exc}"


def _read_notes() -> list[dict]:
    if not NOTES_FILE.exists():
        return []
    try:
        data = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _get_json(url: str, timeout: int = 10) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def run_tool(name: str, arguments: dict) -> str:
    try:
        if name == "get_current_time":
            return get_current_time()
        if name == "add_note":
            return add_note(str(arguments.get("text", "")))
        if name == "list_notes":
            return list_notes()
        if name == "search_wikipedia":
            return search_wikipedia(
                str(arguments.get("query", "")), str(arguments.get("lang", "th"))
            )
    except Exception as exc:
        return f"เรียก tool ไม่สำเร็จ: {exc}"
    return f"ไม่รู้จัก tool: {name}"
