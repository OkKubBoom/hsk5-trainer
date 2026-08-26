"""พาร์ทเขียน — ข้อเรียงคำ (完成句子)

พาร์ทนี้ทำคะแนนได้ง่ายที่สุดในข้อสอบ เพราะเป็นกฎลำดับคำตายตัว ไม่ต้องรู้ศัพท์เยอะ
เฉลยของข้อสอบจริงมักมีหลายแบบที่ถูกต้อง (คั่นด้วย /) จึงต้องรับได้ทุกแบบ
"""
from __future__ import annotations

import random
import re

from .models import ErrorCode, ErrorLog, Question, QuestionStatus, Section

PUNCT = "。，、！？；：“”‘’（）《》 \t\n"


def normalize(text: str) -> str:
    """ตัดเครื่องหมายวรรคตอนและช่องว่างออก เหลือแต่ตัวอักษร

    ผู้เรียนที่เรียงถูกแต่ไม่ได้ใส่จุดท้ายประโยคต้องนับว่าถูก
    เพราะข้อสอบให้คะแนนที่ลำดับคำ ไม่ใช่ที่เครื่องหมาย
    """
    return "".join(ch for ch in (text or "") if ch not in PUNCT)


def accepted_answers(question: Question) -> list[str]:
    """เฉลยที่ยอมรับได้ทุกแบบ — ข้อสอบจริงเขียนคั่นด้วย / เมื่อมีหลายคำตอบ"""
    raw = question.answer_text or ""
    parts = [p.strip() for p in re.split(r"\s*/\s*", raw) if p.strip()]
    return parts or ([raw] if raw else [])


def words_of(question: Question) -> list[str]:
    """คำที่ให้มาเรียง — เก็บไว้ในโจทย์คั่นด้วย /"""
    return [w.strip() for w in (question.prompt_zh or "").split("/") if w.strip()]


def check(question: Question, given: str) -> dict:
    """ตรวจคำตอบ คืนผลพร้อมเฉลยที่ยอมรับได้ทั้งหมด"""
    answers = accepted_answers(question)
    target = normalize(given)
    is_correct = any(normalize(a) == target for a in answers)
    return {
        "is_correct": is_correct,
        "given": given,
        "answers": answers,
        "main_answer": answers[0] if answers else "",
        "other_answers": answers[1:],
    }


def pick_question(*, exclude_ids: list[int] | None = None, seed: int | None = None) -> Question | None:
    """สุ่มข้อเรียงคำหนึ่งข้อ เลี่ยงข้อที่เพิ่งทำไป"""
    qs = Question.objects.filter(qtype="word_order", status=QuestionStatus.ACTIVE)
    if exclude_ids:
        remaining = qs.exclude(pk__in=exclude_ids)
        qs = remaining if remaining.exists() else qs  # ทำครบแล้ววนใหม่
    ids = list(qs.values_list("pk", flat=True))
    if not ids:
        return None
    return Question.objects.filter(pk=random.Random(seed).choice(ids)).first()


def record_result(learner, question: Question, result: dict) -> None:
    """บันทึกลง ErrorLog เมื่อผิด — ให้ข้อที่พลาดไหลเข้าชุดฝึกวันถัดไป

    ใช้สาเหตุ STRUCTURE เสมอ เพราะข้อเรียงคำวัดลำดับคำ ไม่ได้วัดว่ารู้ศัพท์ไหม
    ผู้เรียนที่รู้ศัพท์ครบแต่เรียงผิด ต้องไปทบทวนไวยากรณ์ ไม่ใช่ท่องคำเพิ่ม
    """
    if result["is_correct"]:
        return
    ErrorLog.record(
        learner, ErrorCode.STRUCTURE,
        label=(question.answer_text or question.prompt_zh)[:200],
        section=Section.WRITING, question=question,
    )
