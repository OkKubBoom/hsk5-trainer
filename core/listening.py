"""แยกบทถอดเสียง 听力 ออกเป็นรายข้อ

**ทำไมต้องมีไฟล์นี้**
ข้อสอบฟัง 405 ข้อในคลังตอบไม่ได้เลย เพราะไม่มีเสียงและไม่มีบทพูด
ผู้เรียนเห็นแค่ "(ฟังบทสนทนาแล้วเลือกคำตอบ)" กับตัวเลือกสี่ข้อ ซึ่งเดาล้วน
บทถอดเสียงมีอยู่แล้วใน data/exam_corpus/ แต่เป็นสตริงก้อนเดียวยาว ~3,800 ตัวอักษร
ไฟล์นี้แยกก้อนนั้นออกเป็นรายข้อ เพื่อผูกเข้ากับ Question ที่มีอยู่แล้ว

**โครงของบทถอดเสียง HSK5 (ยืนยันจาก H51001-H51005)**
  第一部分  ข้อ 1-20   บทสนทนาสองบรรทัด + บรรทัด 问：
  第二部分  ข้อ 21-30  บทสนทนาสี่บรรทัด + บรรทัด 问：
            ข้อ 31-45  บทยาวหนึ่งบท ใช้ร่วมกัน 2-4 ข้อ แล้วตามด้วยบรรทัดคำถามที่ไม่มี 问：

**สิ่งที่ยากกว่าที่เห็น**
บทถอดเสียงมาจาก PDF ที่ตัดบรรทัดกลางประโยค เช่น
    本来我连飞机票都买好了，可是因为大雾，航班取消了，
    我只好坐火车过来了。
ถ้าต่อบรรทัดผิด เสียงที่อ่านออกมาจะหยุดกลางประโยค ซึ่งฟังแล้วงงกว่าไม่มีเสียง
จึงต่อบรรทัดที่ไม่ได้ขึ้นต้นด้วย 女：/男： เข้ากับบรรทัดก่อนหน้าเสมอ
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# เลขข้อขึ้นต้นบรรทัด — PDF ใช้จุดเต็มความกว้าง （．） ไม่ใช่จุดปกติ
NUM_LINE = re.compile(r"^(\d{1,2})\s*[．.、]\s*(.*)$")

# หัวบทยาว: 第 31 到 32 题是根据下面一段对话／一段话
PASSAGE_HEAD = re.compile(r"^第\s*(\d{1,2})\s*到\s*(\d{1,2})\s*题是根据下面一段(对话|话)")

SPEAKER = re.compile(r"^(女|男)\s*[：:]")

# เครื่องหมายที่จบประโยคอยู่แล้ว ไม่ต้องเติมจุดซ้ำ
# ถ้าเติม จะได้ "？。" ซึ่งตัวอ่านออกเสียงบางตัวหยุดยาวผิดจังหวะ
SENTENCE_END = "。！？…”）"
QUESTION = re.compile(r"^问\s*[：:]\s*(.*)$")

PART1_HEAD = "第一部分"
PART2_HEAD = "第二部分"
END_MARK = "听力考试现在结束"


@dataclass
class ListeningItem:
    """หนึ่งข้อ พร้อมบทที่ต้องอ่านให้ฟัง"""
    number: int
    kind: str                      # "dialog" | "passage"
    script: str                    # บทที่จะให้อ่านออกเสียง
    question_zh: str               # คำถามที่อ่านต่อท้ายบท
    passage_key: str = ""          # ข้อที่ใช้บทเดียวกัน เช่น "31-32" · ว่าง = ไม่ใช้ร่วม
    lines: list[str] = field(default_factory=list)   # บทแยกบรรทัด ใช้แสดงตอนเฉลย


def _end_stop(text: str) -> str:
    text = text.strip()
    return text if not text or text[-1] in SENTENCE_END else text + "。"


def _clean_lines(raw: str) -> list[str]:
    out = []
    for line in (raw or "").splitlines():
        line = line.strip().replace("　", "")
        if line:
            out.append(line)
    return out


def _join_wrapped(lines: list[str]) -> list[str]:
    """ต่อบรรทัดที่ PDF ตัดกลางประโยคกลับเข้าด้วยกัน

    บรรทัดใหม่ของจริงต้องขึ้นต้นด้วยชื่อผู้พูด บรรทัดอื่นคือส่วนท้ายของบรรทัดก่อน
    ภาษาจีนไม่มีช่องว่างระหว่างคำ จึงต่อกันตรงๆ ไม่ใส่อะไรคั่น
    """
    joined: list[str] = []
    for line in lines:
        # บรรทัด 问：คือคำถามท้ายข้อ ไม่ใช่ส่วนท้ายของประโยคก่อนหน้า
        # ถ้าไม่นับเป็นบรรทัดใหม่ คำถามจะถูกกลืนเข้าไปในบทสนทนาทั้งข้อ
        starts_new = SPEAKER.match(line) or QUESTION.match(line)
        if joined and not starts_new:
            joined[-1] += line
        else:
            joined.append(line)
    return joined


def _split_parts(lines: list[str]) -> tuple[list[str], list[str]]:
    """ตัดหัวประกาศทิ้ง แล้วแยกสองพาร์ท"""
    body = [l for l in lines if not l.startswith(END_MARK)]
    try:
        i1 = next(i for i, l in enumerate(body) if l.startswith(PART1_HEAD))
    except StopIteration:
        return [], []
    try:
        i2 = next(i for i, l in enumerate(body) if l.startswith(PART2_HEAD))
    except StopIteration:
        i2 = len(body)

    def strip_instruction(chunk: list[str]) -> list[str]:
        # "第 1 到 20 题，请选出正确答案。现在开始第 1 题：" ไม่ใช่เนื้อหา
        return [l for l in chunk if "请选出正确答案" not in l]

    return strip_instruction(body[i1 + 1:i2]), strip_instruction(body[i2 + 1:])


def _numbered_blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    """หั่นตามเลขข้อที่ขึ้นต้นบรรทัด

    รับเฉพาะเลขที่เดินหน้าเสมอ — กันบรรทัดในบทที่บังเอิญขึ้นต้นด้วยตัวเลข
    (เช่นบทที่ตัดมาลงท้ายว่า "50 元") มาถูกอ่านว่าเป็นข้อใหม่
    """
    blocks: list[tuple[int, list[str]]] = []
    last = 0
    for line in lines:
        m = NUM_LINE.match(line)
        if m and int(m.group(1)) > last:
            last = int(m.group(1))
            blocks.append((last, [m.group(2)] if m.group(2) else []))
        elif blocks:
            blocks[-1][1].append(line)
    return blocks


def _dialog_items(lines: list[str]) -> list[ListeningItem]:
    """ข้อ 1-30 — หนึ่งเลข = หนึ่งบท จบด้วยบรรทัด 问："""
    items = []
    for number, block in _numbered_blocks(lines):
        block = _join_wrapped(block)
        question = ""
        script_lines = []
        for line in block:
            q = QUESTION.match(line)
            if q:
                question = q.group(1)
            else:
                script_lines.append(line)
        if not script_lines:
            continue
        items.append(ListeningItem(
            number=number, kind="dialog", script="\n".join(script_lines),
            question_zh=question, lines=script_lines,
        ))
    return items


def _passage_items(lines: list[str]) -> list[ListeningItem]:
    """ข้อ 31-45 — บทหนึ่งบทใช้ร่วมกันหลายข้อ คำถามไม่มี 问： นำหน้า"""
    items: list[ListeningItem] = []
    i = 0
    while i < len(lines):
        head = PASSAGE_HEAD.match(lines[i])
        if not head:
            i += 1
            continue
        first, last = int(head.group(1)), int(head.group(2))
        kind_zh = head.group(3)
        i += 1

        body: list[str] = []
        while i < len(lines) and not NUM_LINE.match(lines[i]) and not PASSAGE_HEAD.match(lines[i]):
            body.append(lines[i])
            i += 1

        if kind_zh == "对话":
            body = _join_wrapped(body)
        else:
            # บทเล่าเรื่องไม่มีชื่อผู้พูด ทุกบรรทัดคือประโยคเดียวกันที่ถูกตัด
            body = ["".join(body)] if body else []

        questions: list[tuple[int, str]] = []
        while i < len(lines):
            m = NUM_LINE.match(lines[i])
            if not m or not (first <= int(m.group(1)) <= last):
                break
            questions.append((int(m.group(1)), m.group(2)))
            i += 1

        script = "\n".join(body)
        key = f"{first}-{last}"
        for number, question in questions:
            items.append(ListeningItem(
                number=number, kind="passage", script=script,
                question_zh=question, passage_key=key, lines=body,
            ))
    return items


def parse(transcript: str) -> list[ListeningItem]:
    """แยกบทถอดเสียงทั้งฉบับเป็นรายข้อ เรียงตามเลขข้อ"""
    part1, part2 = _split_parts(_clean_lines(transcript))
    if not part1 and not part2:
        return []

    items = _dialog_items(part1)

    # พาร์ทสองมีสองแบบปนกัน — ตัดตรงหัวบทยาวบรรทัดแรก
    cut = next((i for i, l in enumerate(part2) if PASSAGE_HEAD.match(l)), len(part2))
    items += _dialog_items(part2[:cut])
    items += _passage_items(part2[cut:])

    return sorted(items, key=lambda it: it.number)


def speech_text(item: ListeningItem) -> str:
    """ข้อความที่จะให้เครื่องอ่านออกเสียง — บทก่อน แล้วตามด้วยคำถาม

    ตัดชื่อผู้พูด 女：/男： ออก เพราะข้อสอบจริงใช้คนสองคนพูด ไม่ได้อ่านคำว่า "หญิง"
    ถ้าปล่อยไว้ ผู้เรียนจะได้ยิน "หนวี่" นำทุกประโยค ซึ่งไม่มีในห้องสอบ
    """
    parts = [SPEAKER.sub("", l).strip() for l in item.lines]
    if item.question_zh:
        parts.append(item.question_zh)
    return "".join(_end_stop(p) for p in parts if p)


# ── แยกบทเป็นช่วงพูด เพื่อให้เล่นทีละคน ─────────────────────

def speech_turns(item: ListeningItem) -> list[dict]:
    """แยกบทเป็นช่วงๆ พร้อมบอกว่าใครพูด — ใช้เล่นเสียงทีละช่วง

    **ทำไมต้องแยก ทั้งที่ speech_text() ต่อเป็นก้อนเดียวได้อยู่แล้ว**
    ข้อสอบจริงเป็นบทสนทนาสองคนสลับกันพูด มีจังหวะเงียบคั่น
    แต่ถ้าส่งเป็นสตริงเดียวให้ตัวอ่านออกเสียง จะได้เสียงคนเดียวพูดรวดเดียวไม่หยุด
    ซึ่ง *ฟังยากกว่าของจริง* ไม่ใช่แค่ไม่เหมือน — ผู้เรียนแยกไม่ออกว่าประโยคไหน
    เป็นของใคร แล้วคำถามอย่าง "ผู้ชายหมายความว่าอะไร" ก็ตอบไม่ได้ทั้งที่ฟังออกทุกคำ

    ค่า who: "f" หญิง · "m" ชาย · "q" คำถามท้ายข้อ · "n" บทเล่าเรื่องที่ไม่มีผู้พูด
    """
    turns = []
    for line in item.lines:
        m = SPEAKER.match(line)
        text = SPEAKER.sub("", line).strip()
        if not text:
            continue
        turns.append({"who": {"女": "f", "男": "m"}.get(m.group(1), "n") if m else "n",
                      "text": _end_stop(text)})
    if item.question_zh:
        turns.append({"who": "q", "text": _end_stop(item.question_zh)})
    return turns


# ── ไฟล์เสียงที่อัดไว้ล่วงหน้า ──────────────────────────────

def audio_slug(source_ref: str) -> str:
    """ชื่อไฟล์เสียงของข้อนี้ — "H51001 ข้อ 21" → "H51001-21"

    ผูกกับ source_ref ไม่ใช่กับเลข id เพราะ id เปลี่ยนได้ทุกครั้งที่โหลดข้อมูลใหม่
    แต่ source_ref เป็นเลขข้อจริงของข้อสอบ ซึ่งไม่มีวันเปลี่ยน
    """
    parts = (source_ref or "").replace("ข้อ", " ").split()
    if len(parts) < 2:
        return ""
    return f"{parts[0]}-{parts[-1]}"


def sentence_slug(source_ref: str, index: int) -> str:
    """ชื่อไฟล์เสียงรายประโยคของ 听写 — "H51001 ข้อ 21" ประโยคที่ 0 → "H51001-21-s0" """
    base = audio_slug(source_ref)
    return f"{base}-s{index}" if base else ""


def audio_url(source_ref: str, sentence: int | None = None) -> str:
    """ที่อยู่ไฟล์เสียง — ว่างถ้าข้อนี้ยังไม่มีไฟล์

    ผ่าน static() เสมอ เพราะตอน deploy ชื่อไฟล์ถูกเติมแฮช
    เขียนพาธตายตัวจะพังทุกครั้งที่ deploy ใหม่
    """
    from django.templatetags.static import static

    slug = audio_slug(source_ref) if sentence is None else sentence_slug(source_ref, sentence)
    if not slug:
        return ""
    try:
        return static(f"listening/{slug}.m4a")
    except Exception:
        # prod ใช้ ManifestStaticFilesStorage ซึ่งโยน error เมื่อไม่มีไฟล์นั้น
        # ปล่อยว่างแล้วให้เครื่องเล่นถอยไปใช้ตัวอ่านของเบราว์เซอร์แทน
        return ""
