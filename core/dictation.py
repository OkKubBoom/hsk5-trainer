"""听写 — ฟังแล้วพิมพ์ตาม แล้วเทียบทีละตัวอักษร

**ทำไมต้องมี ทั้งที่สอบ iBT ไม่ต้องเขียนด้วยมือ**
听写 ไม่ได้ฝึกการเขียน แต่ฝึก *การแยกเสียงออกเป็นคำ* ซึ่งคือทักษะที่ขาดจริง
คนที่ฟังข้อสอบแล้วได้ยินเป็นเสียงยาวๆ ก้อนเดียว แยกไม่ออกว่าตรงไหนจบคำ
จะตอบข้อฟังไม่ได้ต่อให้รู้ศัพท์ครบทุกคำ — และการเลือก ก-ง ปิดปัญหานี้ไว้
เพราะเดาถูกได้ 25% โดยไม่ต้องแยกเสียงเลย

**ป้ายชนิดข้อผิด** ติดเฉพาะที่พิสูจน์ได้จากข้อมูลที่มี
เสียงพ้อง (同音字) ติดป้ายต่อเมื่อ *ทั้งสองตัว* มีพินอินอยู่ในคลังของเราและตรงกัน
ไม่เดาจากรูปร่างตัวอักษรหรือจากความน่าจะเป็น เพราะป้ายที่ผิดสอนผิด
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache

from . import listen_explain
from .models import Question, QuestionStatus, Section, VocabItem

HAN = re.compile(r"[一-鿿]")

# ประโยคที่สั้นกว่านี้ฝึกอะไรไม่ได้ ยาวกว่านี้จำไม่ไหวใน 1-2 รอบ
MIN_CHARS = 8
MAX_CHARS = 30

TONE_MARKS = str.maketrans("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ", "aaaaeeeeiiiioooouuuuuuuu")


def hanzi_only(text: str) -> str:
    """เทียบเฉพาะตัวอักษรจีน — เครื่องหมายวรรคตอนไม่ได้อยู่ในเสียงที่ได้ยิน

    ถ้านับจุลภาคด้วย คนที่พิมพ์ถูกทุกตัวแต่ไม่ใส่จุลภาคจะถูกหักคะแนน
    ทั้งที่ฟังออกครบแล้ว ซึ่งไม่ใช่สิ่งที่ 听写 ต้องการวัด
    """
    return "".join(HAN.findall(text or ""))


@lru_cache(maxsize=1)
def _char_pinyin() -> dict[str, str]:
    """พินอินของตัวอักษรเดี่ยวเท่าที่คลังของเรามี (ราว 400 ตัว)

    ไม่ครบทุกตัวโดยธรรมชาติ — จึงใช้ *ยืนยัน* ว่าเป็นเสียงพ้องเท่านั้น
    ไม่ใช้สรุปว่า "ไม่ใช่เสียงพ้อง" เพราะการไม่มีข้อมูลไม่ใช่หลักฐาน
    """
    rows = VocabItem.objects.filter(hanzi__regex=r"^.$").exclude(pinyin="")
    return {v.hanzi: v.pinyin.strip().lower() for v in rows}


def _same_sound(a: str, b: str) -> bool:
    table = _char_pinyin()
    pa, pb = table.get(a), table.get(b)
    if not pa or not pb:
        return False
    # ตัดวรรณยุกต์ออกก่อนเทียบ — 在 zài กับ 再 zài เสียงเดียวกัน
    # ส่วน 是 shì กับ 时 shí ต่างกันแค่วรรณยุกต์ ซึ่งคนไทยสับสนบ่อยพอกัน
    return pa.translate(TONE_MARKS) == pb.translate(TONE_MARKS)


def compare(expected: str, typed: str) -> dict:
    """เทียบทีละตัวอักษร คืนรายการเทียบที่เทมเพลตแสดงได้ตรงๆ

    ใช้ SequenceMatcher เพราะการเทียบตำแหน่งตรงๆ พังทันทีที่พิมพ์ตกไปหนึ่งตัว
    — ตัวที่เหลือทั้งประโยคจะถูกนับว่าผิดหมด ทั้งที่พลาดจริงแค่ตัวเดียว
    """
    want = hanzi_only(expected)
    got = hanzi_only(typed)
    ops, wrong = [], 0

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, want, got, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                ops.append({"type": "ok", "expected": want[k], "got": want[k]})
        elif tag == "replace":
            for n in range(max(i2 - i1, j2 - j1)):
                w = want[i1 + n] if i1 + n < i2 else ""
                g = got[j1 + n] if j1 + n < j2 else ""
                kind = "homophone" if w and g and _same_sound(w, g) else "wrong"
                if not w:
                    kind = "extra"
                elif not g:
                    kind = "missing"
                ops.append({"type": kind, "expected": w, "got": g})
                wrong += 1
        elif tag == "delete":
            for k in range(i1, i2):
                ops.append({"type": "missing", "expected": want[k], "got": ""})
                wrong += 1
        elif tag == "insert":
            for k in range(j1, j2):
                ops.append({"type": "extra", "expected": "", "got": got[k]})
                wrong += 1

    total = len(want) or 1
    return {
        "ops": ops,
        "expected": want,
        "typed": got,
        "wrong": wrong,
        "correct": max(0, len(want) - sum(1 for o in ops if o["type"] in ("wrong", "missing", "homophone"))),
        "accuracy": round(max(0, total - wrong) / total * 100, 1),
        "perfect": wrong == 0 and len(want) == len(got),
        "homophones": [o for o in ops if o["type"] == "homophone"],
    }


def sentence_rows(question: Question) -> list[dict]:
    """ประโยคที่ฝึกได้ พร้อมบอกว่าใครพูดประโยคนั้น

    แยกจาก audio_turns ทีละช่วง ไม่ใช่ตัดจากบทที่ต่อกันแล้ว เพราะต้องรู้ว่า
    ประโยคนี้เป็นของผู้หญิงหรือผู้ชาย จะได้อัดเสียงด้วยเสียงที่ถูกคน
    ถ้าใช้เสียงผิดคน ผู้เรียนจะจำเสียงคำผิดไปเลย ซึ่งแย่กว่าไม่มีเสียง

    ข้อเก่าที่ยังไม่มี audio_turns ถอยไปตัดจากบทรวมเหมือนเดิม (ไม่รู้ว่าใครพูด)
    """
    turns = question.audio_turns or []
    if not turns:
        body = listen_explain.body_only(question)
        return [{"index": i, "text": s, "who": "n"}
                for i, s in enumerate(_fit(listen_explain.sentences(body)))]

    rows = []
    for turn in turns:
        if turn.get("who") == "q":
            continue                       # คำถามอยู่บนจอให้อ่านแล้ว ไม่ใช่สิ่งที่ต้องฟัง
        for text in _fit(listen_explain.sentences(turn.get("text", ""))):
            rows.append({"index": len(rows), "text": text, "who": turn.get("who", "n")})
    return rows


def _fit(items) -> list[str]:
    """เก็บเฉพาะประโยคที่ยาวพอดี — สั้นไปฝึกอะไรไม่ได้ ยาวไปจำไม่ไหว"""
    return [s for s in items if MIN_CHARS <= len(hanzi_only(s)) <= MAX_CHARS]


def sentences_of(question: Question) -> list[str]:
    """ประโยคในบทของข้อนี้ที่ยาวพอดีสำหรับ 听写"""
    return [r["text"] for r in sentence_rows(question)]


def pool():
    return (
        Question.objects
        .filter(section=Section.LISTENING, status=QuestionStatus.ACTIVE)
        .exclude(audio_script="")
    )


def pick(*, exclude: list[str] | None = None, seed: int | None = None) -> dict | None:
    """สุ่มประโยคหนึ่งประโยคมาให้ฝึก

    คืน key เป็น "<question_id>:<index>" เพื่อให้จำได้ว่าเคยฝึกประโยคไหนไปแล้ว
    ไม่ใช่จำแค่ว่าเคยเจอข้อไหน เพราะข้อเดียวมีหลายประโยคที่ฝึกได้
    """
    import random

    rng = random.Random(seed)
    exclude = set(exclude or [])
    ids = list(pool().values_list("pk", flat=True))
    if not ids:
        return None

    rng.shuffle(ids)
    fallback = None
    for qid in ids[:60]:
        question = Question.objects.filter(pk=qid).first()
        for i, sentence in enumerate(sentences_of(question)):
            item = {"question": question, "index": i, "sentence": sentence,
                    "key": f"{qid}:{i}"}
            fallback = fallback or item
            if item["key"] not in exclude:
                return item
    return fallback   # ฝึกครบทุกประโยคแล้ว วนกลับมาใหม่


def total_sentences() -> int:
    """จำนวนประโยคทั้งหมดที่ฝึกได้ — ใช้บอกความคืบหน้า"""
    return sum(len(sentences_of(q)) for q in pool().only("audio_script", "prompt_zh"))
