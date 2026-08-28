"""การแสดงบทอ่านและช่องว่าง — ใช้ร่วมกันทั้งชุดฝึกรายวันและข้อสอบจำลอง

มีไฟล์นี้เพราะเคยเขียนตรรกะนี้ไว้เฉพาะในเทมเพลตของข้อสอบจำลอง
ชุดฝึกรายวันจึงไม่แสดงบทอ่านเลย และผู้เรียนเจอคำถามอย่าง
"根据上文…" (ตามบทความข้างต้น) โดยไม่มีบทความให้อ่าน = ตอบไม่ได้ ต้องเดา
กระทบ 315 ข้อจาก 417 ข้ออ่านทั้งหมด

สามชนิดข้อ สามวิธีแสดง:

  阅读第一部分 (选词填空)   บทอ่านมีหลายช่องว่าง ถามทีละช่อง
                          → ต้องบอกว่ากำลังตอบช่องไหน ไม่งั้นเดาล้วน
  阅读第二部分 (61-70)      บทอ่านสั้น ไม่มีคำถามแยก เลือกข้อที่ตรงกับเนื้อหา
                          → ต้องบอกให้ชัดว่าไม่มีคำถาม ไม่งั้นผู้เรียนหาคำถามที่ไม่มีอยู่
  阅读第三部分 (71-90)      บทอ่านยาว มีหลายคำถาม
                          → ต้องแสดงบทอ่าน แล้วตามด้วยคำถามของข้อนั้น
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from django.utils.html import escape
from django.utils.safestring import mark_safe

# เลขข้ออยู่ท้าย source_ref เช่น "H51001 ข้อ 46"
_REF_NUMBER = re.compile(r"ข้อ\s*(\d+)\s*$")


def blank_number(question) -> int | None:
    """เลขช่องว่างที่ข้อนี้กำลังถาม — เก็บอยู่ใน source_ref ไม่มีฟิลด์ของตัวเอง"""
    m = _REF_NUMBER.search(question.source_ref or "")
    return int(m.group(1)) if m else None


def group_blanks(question) -> list[int]:
    """เลขช่องว่างทั้งหมดในบทอ่านเดียวกัน — ใช้ทำให้ช่องอื่นจางลง"""
    if not question.group_id:
        n = blank_number(question)
        return [n] if n else []
    numbers = [blank_number(q) for q in question.group.questions.all()]
    return sorted(n for n in numbers if n)


@dataclass
class ReadingView:
    """สิ่งที่หน้าเว็บต้องรู้เพื่อแสดงโจทย์หนึ่งข้อให้ครบ"""
    instruction: str          # คำสั่ง — ต้องเด่น ไม่ใช่ตัวเทาเล็กท้ายป้าย
    passage_html: str         # บทอ่าน (ไฮไลต์ช่องที่กำลังตอบแล้ว) — ว่างได้
    prompt: str               # ตัวคำถาม — ว่างได้ถ้าชนิดข้อไม่มีคำถาม
    blank_no: int | None      # ช่องที่กำลังตอบ
    total_blanks: int         # จำนวนช่องทั้งหมดในบทอ่านนี้
    # จริงหรือไม่ว่าข้อนี้ "ไม่มีคำถาม" ตามรูปแบบข้อสอบ — ใช้กับ 阅读第二部分 เท่านั้น
    # ข้อเติมคำก็ไม่มีคำถามเป็นประโยค แต่มีช่องที่ระบุชัดอยู่แล้ว จึงไม่ต้องบอกซ้ำ
    answers_whole_passage: bool = False

    @property
    def has_passage(self):
        return bool(self.passage_html)

    @property
    def has_prompt(self):
        return bool(self.prompt)


def highlight_blanks(passage: str, current: int | None, others: list[int]) -> str:
    """ทำให้ช่องที่กำลังตอบเด่น และช่องอื่นจางลง

    ต้อง escape ก่อนแล้วค่อยใส่แท็ก — บทอ่านมาจากไฟล์ข้อสอบ ไม่ใช่ค่าที่เราคุม
    การ escape ไม่แตะตัวเลขและขีดล่าง จึงหาช่องว่างหลัง escape ได้ตามปกติ
    """
    html = escape(passage)
    if not html:
        return ""

    def wrap(number: int, css: str) -> None:
        nonlocal html
        # ช่องว่างในข้อสอบเขียนได้หลายแบบ: "__46__" · "  46  " · "46"
        # (?<!\d) กับ (?!\d) กันไม่ให้ไปโดนเลขที่ยาวกว่า เช่น 46 ใน 460
        pattern = re.compile(rf"(?<!\d)(_*\s*){number}(\s*_*)(?!\d)")
        html = pattern.sub(
            lambda m: f'<span class="{css}">{m.group(1)}{number}{m.group(2)}</span>',
            html, count=1,
        )

    for n in others:
        if n != current:
            wrap(n, "blank other")
    if current:
        wrap(current, "blank now")
    return mark_safe(html)


def build(question) -> ReadingView:
    """แปลงหนึ่งคำถามให้เป็นสิ่งที่แสดงได้ครบ ไม่ว่าจะเป็นชนิดไหน"""
    qtype = question.qtype
    group = question.group if question.group_id else None
    passage = (group.passage_zh if group else "") or ""
    prompt = question.prompt_zh or ""
    blanks = group_blanks(question)
    current = blank_number(question)

    if qtype == "synonym_cloze":
        # ข้อชนิดนี้เก็บบทอ่านซ้ำไว้ใน prompt_zh ของทุกข้อในกลุ่ม
        # ถ้าแสดงทั้งสองที่ ผู้เรียนจะอ่านบทความเดียวกันสองรอบ
        passage = passage or prompt
        instruction = (
            f"เลือกคำที่เหมาะกับช่อง {current} ที่สุด" if current
            else "เลือกคำที่เหมาะกับช่องว่างที่สุด"
        )
        return ReadingView(
            instruction=instruction,
            passage_html=highlight_blanks(passage, current, blanks),
            prompt="", blank_no=current, total_blanks=len(blanks),
        )

    if passage:
        # บทอ่านยาวที่มีหลายคำถาม — แสดงบทอ่านก่อน แล้วตามด้วยคำถามของข้อนี้
        return ReadingView(
            instruction=question.prompt_th or "อ่านบทความแล้วเลือกคำตอบ",
            passage_html=highlight_blanks(passage, None, []),
            prompt=prompt, blank_no=None, total_blanks=0,
        )

    if qtype == "reading_mc":
        # 阅读第二部分 — prompt_zh คือบทอ่าน และ *ไม่มีคำถาม* ตามรูปแบบข้อสอบจริง
        # ต้องบอกให้ชัด ไม่งั้นผู้เรียนจะมองหาคำถามที่ไม่มีอยู่ (น้องเจอมาแล้ว)
        return ReadingView(
            instruction=question.prompt_th or "อ่านแล้วเลือกข้อที่ตรงกับเนื้อหา",
            passage_html=highlight_blanks(prompt, None, []),
            prompt="", blank_no=None, total_blanks=0,
            answers_whole_passage=True,
        )

    # ข้อสั้นทั่วไป (ฟัง / เรียงคำ) — โจทย์คือคำถามตรงๆ ไม่มีบทอ่าน
    return ReadingView(
        instruction=question.prompt_th or "เลือกคำตอบที่ถูกต้อง",
        passage_html="", prompt=prompt, blank_no=None, total_blanks=0,
    )
