"""ชั้นที่ 2 — ให้ Claude *สังเกต* งานเขียน ไม่ใช่ให้คะแนน

โมเดลรายงานว่าผิดตรงไหนเพราะอะไร แล้ว core/essay.py ตัดสินระดับจากผลนั้น
เหตุผลที่แยกกันอยู่ในหัวไฟล์ essay.py

**สิ่งที่ส่งออกไปนอกระบบ**
  ส่ง:    งานเขียนของผู้เรียนเอง · คำที่โจทย์กำหนด (สุ่มจากคลังเราเอง)
  ไม่ส่ง: ข้อความข้อสอบลิขสิทธิ์ · บทอ่าน · เฉลย · คำอธิบายในระบบ
          ชื่อผู้เรียน · อีเมล · ข้อมูลใดที่ระบุตัวตนได้
ผู้เรียนต้องกดยินยอมก่อนใช้ครั้งแรก และมีบรรทัดบอกอยู่บนหน้าจอตลอด

ระบบมีสองทางที่เขียนผลลงที่เดียวกัน:
  ทางหลัก  ผู้เรียนกดขอ → เจ้าของเอาพรอมต์ไปถาม Claude เอง → วางผล JSON กลับมา
           ไม่ต้องมีกุญแจ ไม่มีค่าใช้จ่ายต่อครั้ง เจ้าของเห็นผลก่อนผู้เรียน
  ทางเสริม เรียก API ตรงๆ — เปิดใช้เมื่อตั้ง ANTHROPIC_API_KEY เท่านั้น

**ห้ามสร้าง client ที่ระดับโมดูล** — Dockerfile รัน collectstatic ตอน build
โดยไม่มี ANTHROPIC_API_KEY ถ้าสร้างตอน import จะทำให้ build image พัง
"""
from __future__ import annotations

import json
import os

# รุ่นที่ใช้ตรวจ — งานคือชี้ว่า *ผิดเพราะอะไร* ตาม D8
# ถ้าคำอธิบายผิด ผู้เรียนจำผิดไปสอบ ซึ่งแย่กว่าไม่มีระบบตรวจเลย จึงไม่ลดรุ่นเพื่อประหยัด
MODEL = "claude-opus-5"
MAX_TOKENS = 4000

# ชื่อที่ติดไว้ในช่อง "ตรวจโดย" ของแต่ละทาง — ต้องแยกกันให้เห็น
# เพราะทางถ่ายทอดมีคนอ่านผลก่อนวางลงระบบ ส่วนทาง API ไม่มีใครดูเลย
RELAY_LABEL = f"{MODEL} · เจ้าของระบบถามให้"

# ชนิดข้อผิด — ชั้นที่ 3 นับจากคำนำหน้า typo_ กับ grammar_ จึงห้ามเปลี่ยนคำนำหน้า
ISSUE_KINDS = [
    "typo_homophone", "typo_form",
    "grammar_order", "grammar_missing", "grammar_extra", "grammar_wrong_word",
    "grammar_de_particle", "grammar_ba_bei", "grammar_measure_word",
    "grammar_separable_verb",
    "collocation", "punctuation",
]

OBSERVATION_SCHEMA = {
    "type": "object",
    "properties": {
        "coherent_logical": {"type": "boolean", "description": "内容连贯且合逻辑 หรือไม่"},
        "image_relevant": {"type": ["boolean", "null"], "description": "ข้อ 100 เท่านั้น ข้อ 99 ให้เป็น null"},
        "content_rich": {"type": "boolean", "description": "内容丰富 หรือไม่"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "span": {"type": "string", "description": "ข้อความรอบจุดผิด คัดจากงานเขียนตรงตัว"},
                    "wrong": {"type": "string"},
                    "right": {"type": "string"},
                    "why_th": {"type": "string", "description": "อธิบายเป็นภาษาไทยว่าผิดเพราะอะไร"},
                    "kind": {"type": "string", "enum": ISSUE_KINDS},
                    "certainty": {"type": "string", "enum": ["sure", "unsure"]},
                },
                "required": ["span", "wrong", "right", "why_th", "kind", "certainty"],
            },
        },
        "suggestions_th": {"type": "array", "items": {"type": "string"}},
        "strengths_th": {"type": "array", "items": {"type": "string"}},
        "next_step_th": {"type": "string"},
    },
    "required": ["coherent_logical", "content_rich", "issues",
                 "suggestions_th", "strengths_th", "next_step_th"],
}

SYSTEM = """คุณคือผู้ช่วยตรวจงานเขียนภาษาจีนสำหรับผู้เรียนไทยที่เตรียมสอบ HSK5 พาร์ท 书写第二部分

หน้าที่ของคุณคือ **รายงานข้อสังเกต** ไม่ใช่ให้คะแนน ระบบจะตัดสินระดับเองจากสิ่งที่คุณรายงาน

กฎที่ห้ามฝ่าฝืน:
1. ห้ามตัดสินคุณภาพความคิด ความลึกซึ้ง หรือมุมมอง — เอกสารเกณฑ์ของ 汉办 ระบุไว้ตรงๆ ว่า
   ผู้ตรวจสนใจความถูกต้องและความลื่นไหลของภาษา ไม่ใช่ความสูงต่ำของความคิด
2. ประโยคที่ถูกไวยากรณ์อยู่แล้วแต่ยังเขียนให้ดีกว่านี้ได้ ห้ามนับเป็นข้อผิด
   ให้ใส่ใน suggestions_th แทน
3. ห้ามตัดสินว่าเนื้อหาจริงหรือแต่ง ผู้เรียนแต่งเรื่องได้
4. ไม่มั่นใจให้ใส่ certainty เป็น "unsure" แทนการฟันธง
5. ห้ามนับจำนวนตัวอักษร ระบบนับให้แล้ว
6. คำอธิบายทุกบรรทัดเป็นภาษาไทย ยกตัวอย่างประโยคจีนประกอบได้
7. span และ wrong ต้องคัดจากงานเขียนตรงตัว ห้ามเรียบเรียงใหม่ ไม่งั้นผู้เรียนหาจุดไม่เจอ

ผู้เรียนเป็นคนไทย ข้อผิดที่พบบ่อยคือการวางส่วนขยาย เพราะภาษาไทยวางไว้หลังคำหลัก
แต่ภาษาจีนวางไว้หน้า — ถ้าเจอให้ใช้ kind เป็น grammar_order และอธิบายกฎให้ชัด"""


class GraderUnavailable(Exception):
    """ตรวจไม่ได้ตอนนี้ — ระบบต้องบอกผู้เรียนตรงๆ ไม่ใช่เงียบหรือพัง"""


def is_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def build_prompt(*, text_zh: str, task_no: int, required_words: list[str],
                 char_count: int, missing: list[str]) -> str:
    """ประกอบโจทย์ — บอกผลการนับของเราไปด้วย โมเดลจะได้ไม่ต้องนับเอง"""
    lines = [
        f"ข้อ {task_no} ของ 书写第二部分",
        f"ระบบนับให้แล้ว: {char_count} ตัวอักษรจีน (เกณฑ์ 80 字左右)",
    ]
    if task_no == 99:
        lines.append("คำที่โจทย์กำหนดให้ใช้ครบ: " + " ".join(required_words))
        lines.append(
            "ระบบตรวจแล้ว: " +
            ("ใช้ครบทุกคำ" if not missing else "ยังไม่ได้ใช้ " + " ".join(missing))
        )
    lines += ["", "งานเขียนของผู้เรียน:", text_zh]
    return "\n".join(lines)


def observe(*, text_zh: str, task_no: int, required_words: list[str],
            char_count: int, missing: list[str]) -> tuple[dict, dict]:
    """เรียก Claude ให้สังเกตงานเขียน คืน (ผลสังเกต, จำนวนโทเคนที่ใช้)

    ทุกความล้มเหลวถูกแปลงเป็น GraderUnavailable พร้อมข้อความไทยที่บอกทางออก
    เพราะผู้เรียนไม่ควรเจอข้อความ error ดิบของไลบรารี
    """
    if not is_configured():
        raise GraderUnavailable(
            "ยังไม่ได้ตั้งค่ากุญแจสำหรับเรียกตัวตรวจ — "
            "งานเขียนถูกบันทึกไว้แล้ว กดตรวจใหม่ได้เมื่อเจ้าของระบบตั้งค่าเสร็จ"
        )
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - ขึ้นกับสภาพเครื่อง
        raise GraderUnavailable("ยังไม่ได้ติดตั้งไลบรารีสำหรับเรียกตัวตรวจบนเซิร์ฟเวอร์นี้") from exc

    # สร้าง client ในฟังก์ชันเสมอ ไม่ใช่ที่ระดับโมดูล — ดูเหตุผลที่หัวไฟล์
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=120.0)
    prompt = build_prompt(text_zh=text_zh, task_no=task_no, required_words=required_words,
                          char_count=char_count, missing=missing)

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "name": "report_observation",
                "description": "รายงานข้อสังเกตจากงานเขียน",
                "input_schema": OBSERVATION_SCHEMA,
            }],
            tool_choice={"type": "tool", "name": "report_observation"},
        )
    except Exception as exc:
        raise GraderUnavailable(_friendly(exc)) from exc

    observation = next(
        (b.input for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
    if not observation:
        raise GraderUnavailable("ตัวตรวจตอบกลับมาในรูปแบบที่อ่านไม่ได้ ลองกดตรวจใหม่อีกครั้ง")

    usage = {
        "input_tokens": getattr(resp.usage, "input_tokens", 0),
        "output_tokens": getattr(resp.usage, "output_tokens", 0),
    }
    return _clean(observation, text_zh), usage


def _clean(observation: dict, text_zh: str) -> dict:
    """กันข้อผิดที่โมเดลแต่งขึ้นเองโดยไม่มีอยู่ในงานเขียนจริง

    ถ้า wrong ไม่ปรากฏในข้อความที่ผู้เรียนเขียน แสดงว่าโมเดลเรียบเรียงใหม่
    ผู้เรียนจะหาจุดนั้นไม่เจอ และอาจแก้สิ่งที่ตัวเองไม่ได้เขียนผิด
    """
    kept, dropped = [], 0
    for issue in observation.get("issues") or []:
        wrong = (issue.get("wrong") or "").strip()
        if wrong and wrong not in text_zh:
            dropped += 1
            continue
        kept.append(issue)
    observation["issues"] = kept
    if dropped:
        observation["dropped_issues"] = dropped
    return observation


def _friendly(exc: Exception) -> str:
    name = type(exc).__name__
    if "RateLimit" in name:
        return "ตัวตรวจกำลังถูกเรียกถี่เกินไป รออีกสักครู่แล้วกดตรวจใหม่"
    if "Authentication" in name or "PermissionDenied" in name:
        return "กุญแจสำหรับเรียกตัวตรวจใช้ไม่ได้ ต้องให้เจ้าของระบบตรวจสอบ"
    if "Timeout" in name or "APIConnection" in name:
        return "เรียกตัวตรวจไม่สำเร็จภายในเวลาที่กำหนด งานเขียนถูกบันทึกแล้ว กดตรวจใหม่ได้"
    return "ตรวจไม่สำเร็จตอนนี้ งานเขียนถูกบันทึกไว้แล้ว กดตรวจใหม่ได้"


# ── ทางหลัก: ให้เจ้าของระบบเอาไปถาม Claude เองแล้ววางผลกลับมา ──

def full_prompt(*, text_zh: str, task_no: int, required_words: list[str],
                char_count: int, missing: list[str]) -> str:
    """พรอมต์เต็มที่ก๊อปไปวางใน Claude ได้เลย

    รวมคำสั่งระบบ โจทย์ และโครง JSON ไว้ในก้อนเดียว เพราะเจ้าของระบบจะก๊อปทีเดียว
    ไม่ควรต้องประกอบเอง — ทุกขั้นที่ต้องทำเองคือโอกาสที่จะทำพลาด
    """
    schema_hint = json.dumps(OBSERVATION_SCHEMA, ensure_ascii=False, indent=1)
    return "\n".join([
        SYSTEM,
        "",
        "── โจทย์และงานเขียน ──",
        build_prompt(text_zh=text_zh, task_no=task_no, required_words=required_words,
                     char_count=char_count, missing=missing),
        "",
        "── รูปแบบคำตอบ ──",
        "ตอบกลับเป็น JSON ก้อนเดียวตาม schema นี้ ห้ามมีข้อความอื่นนอกก้อน JSON",
        "```json",
        schema_hint,
        "```",
    ])


class PasteError(ValueError):
    """ผลที่วางกลับมาอ่านไม่ได้ — ต้องบอกเจ้าของระบบว่าผิดตรงไหน"""


def parse_pasted(raw: str) -> dict:
    """แกะ JSON ที่เจ้าของระบบวางกลับมา

    ยอมรับทั้งก้อน JSON ล้วน และก้อนที่ห่อด้วย ```json เพราะคนก๊อปมักติดมาด้วย
    """
    text = (raw or "").strip()
    if not text:
        raise PasteError("ยังไม่ได้วางอะไรมา")

    if "```" in text:
        parts = text.split("```")
        text = next((p for p in parts if p.strip().startswith(("{", "json"))), text)
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise PasteError("หาก้อน JSON ไม่เจอ — ต้องมีวงเล็บปีกกาเปิดและปิด")

    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise PasteError(f"อ่าน JSON ไม่ได้ที่บรรทัด {exc.lineno} — {exc.msg}") from exc

    missing = [k for k in ("coherent_logical", "content_rich", "issues") if k not in data]
    if missing:
        raise PasteError("ขาดข้อมูลที่จำเป็น: " + " · ".join(missing))
    if not isinstance(data.get("issues"), list):
        raise PasteError("ช่อง issues ต้องเป็นรายการ")

    for key in ("suggestions_th", "strengths_th"):
        data.setdefault(key, [])
    data.setdefault("next_step_th", "")
    return data
