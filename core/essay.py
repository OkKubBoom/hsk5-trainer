"""เรียงความ 书写第二部分 — ตรรกะสามชั้น

ชั้นที่ 1  Python นับ         จำนวนตัวอักษร · ใช้คำครบไหม   ← โมเดลนับผิดประจำ ห้ามให้ทำ
ชั้นที่ 2  Claude สังเกต       ผิดตรงไหน เพราะอะไร            ← ดู essay_grader.py
ชั้นที่ 3  Python ตัดสินระดับ   จากผลสองชั้นบน                ← ห้ามถามโมเดลว่า "ให้กี่คะแนน"

**ทำไมไม่ให้โมเดลให้คะแนนเอง**
เกณฑ์ทางการของ 汉办 ไม่ได้แบ่งเป็นด้านแล้วให้คะแนนรายด้าน แต่แบ่งเป็น "ช่วง" สี่ระดับ
โดยมีเงื่อนไขที่ตรวจได้ตรงๆ เช่น 高档 บังคับ 无错别字 พร้อมกับ 无语法错误
ถ้าให้โมเดลตัดสิน มันจะใจอ่อนและให้ระดับสูงกับงานที่มีข้อผิด
พอผู้เรียนแก้คำแย้งแล้ว ระบบต้องคำนวณระดับใหม่ได้เองด้วย ซึ่งทำไม่ได้ถ้าคะแนนมาจากโมเดล

แหล่งเกณฑ์: chinesetest.cn/userfiles/file/HSK-pingfen.pdf และ dagang/HSK5.pdf
"""
from __future__ import annotations

import random
import re

HAN = re.compile(r"[一-鿿]")

# 80 字左右 ตามที่โจทย์จริงระบุ
TARGET_CHARS = 80

# จำนวนคำที่โจทย์ข้อ 99 กำหนดให้ใช้ครบ
REQUIRED_WORD_COUNT = 5

# "较多错别字" ในเกณฑ์ 低档 ไม่ระบุตัวเลข — ยืมเกณฑ์จากหัวข้ออื่นในเอกสารฉบับเดียวกัน
# **นี่คือการอนุมาน ไม่ใช่ตัวบท** ต้องติดป้ายบอกผู้เรียนเมื่อระดับถูกตัดสินด้วยเงื่อนไขนี้
MANY_TYPOS = 3

BAND_LABEL = {
    "zero": "0分 — ไม่ได้เขียน",
    "low": "低档分 — ระดับต้น",
    "mid": "中档分 — ระดับกลาง",
    "high": "高档分 — ระดับสูง",
}

# 汉办 ไม่เคยประกาศว่าแต่ละช่วงคือกี่คะแนนจาก 30 และคะแนนดิบถูกแปลงเป็น 标准分
# ก่อนออกใบผลอีกชั้น → ตัวเลขนี้เป็นการประมาณของระบบเท่านั้น ห้ามแสดงว่าเป็นคะแนนสอบ
BAND_ESTIMATE_30 = {"zero": 0, "low": 6, "mid": 18, "high": 27}


def count_chars(text: str) -> int:
    """นับเฉพาะตัวอักษรจีน — โมเดลภาษานับตัวอักษรผิดเป็นประจำ ต้องนับฝั่งเราเสมอ"""
    return len(HAN.findall(text or ""))


def missing_words(text: str, required: list[str]) -> list[str]:
    """คำที่โจทย์กำหนดแต่ยังไม่ได้ใช้ — เงื่อนไขตรงตัวของเกณฑ์ข้อ 99"""
    return [w for w in (required or []) if w and w not in (text or "")]


def pick_words(vocab_pool, count: int = REQUIRED_WORD_COUNT, *, seed: int | None = None) -> list[str]:
    """สุ่มคำสำหรับโจทย์ข้อ 99 จากคลังของเราเอง

    ไม่ใช้โจทย์จริงจาก data/exam_corpus/ เพราะเป็นของลิขสิทธิ์และห้ามส่งออกนอกระบบ
    คลังคำศัพท์ของเราเป็น commercial_safe อยู่แล้ว จึงส่งให้ตรวจได้
    """
    words = list(vocab_pool)
    if len(words) <= count:
        return [w.hanzi for w in words]
    return [w.hanzi for w in random.Random(seed).sample(words, count)]


def decide_band(*, char_count: int, missing: list[str], task_no: int,
                observation: dict) -> dict:
    """ตัดสินระดับตามเกณฑ์ 汉办 — Python ล้วน ไม่มีโมเดลเกี่ยวข้อง

    observation คือผลจากชั้นที่ 2 (ดู essay_grader.EssayObservation)
    """
    issues = observation.get("issues") or []
    # ข้อที่โมเดลบอกว่าไม่มั่นใจ ไม่ถูกนับในการตัดสิน — ยังแสดงให้ผู้เรียนดูได้
    sure = [i for i in issues if i.get("certainty") == "sure"]
    typo_count = sum(1 for i in sure if str(i.get("kind", "")).startswith("typo"))
    grammar_errors = sum(1 for i in sure if str(i.get("kind", "")).startswith("grammar"))

    coherent = bool(observation.get("coherent_logical"))
    content_rich = bool(observation.get("content_rich"))
    length_ok = char_count >= TARGET_CHARS
    task_ok = (not missing) if task_no == 99 else bool(observation.get("image_relevant"))

    note = ""
    if char_count == 0:
        band = "zero"
    elif (not task_ok) or (not coherent) or typo_count >= MANY_TYPOS:
        band = "low"
        if task_ok and coherent and typo_count >= MANY_TYPOS:
            note = f"เกณฑ์ 较多错别字 ไม่ระบุตัวเลขในตัวบท ระบบใช้ {MANY_TYPOS} จุดขึ้นไป — เป็นการตีความ"
        elif not task_ok and coherent:
            note = "ตัวบทเขียนเงื่อนไข 低档 ต่อกันด้วยจุลภาค อ่านได้ว่าต้องเข้าครบทุกข้อ ระบบตีความแยกข้อ"
    elif task_ok and typo_count == 0 and grammar_errors == 0 and coherent and content_rich:
        band = "high"
    else:
        band = "mid"

    # 篇幅不够 อยู่ในเกณฑ์ 中档 ของทั้งสองข้อ — ถ้าไม่ดักไว้ งานสั้นที่ไม่มีข้อผิดจะได้ 高档
    if band == "high" and not length_ok:
        band = "mid"
        note = f"เขียนได้ {char_count} ตัวอักษร ยังไม่ถึง {TARGET_CHARS} — เกณฑ์ระบุ 篇幅不够 ไว้ที่ระดับกลาง"

    return {
        "band": band,
        "band_label": BAND_LABEL[band],
        "task_ok": task_ok,
        "missing_words": missing,
        "typo_count": typo_count,
        "grammar_errors": grammar_errors,
        "coherent": coherent,
        "content_rich": content_rich,
        "length_ok": length_ok,
        "char_count": char_count,
        "estimated_30": BAND_ESTIMATE_30[band],
        "estimate_is_ai": True,
        "band_rule_note": note,
        "task_no": task_no,
        "standard": "2.0",
    }
