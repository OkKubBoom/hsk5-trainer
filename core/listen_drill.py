"""ฝึกพาร์ทฟังทีละข้อ

**ทำไมต้องแยกจากชุดฝึกรายวัน**
ชุดรายวันจำกัดข้อสอบจริงไว้ 10 ข้อ (settings.DRILL_MAX_QUESTIONS) เพื่อให้ที่ว่าง
ตกเป็นของคำศัพท์ ซึ่งถูกต้องตอนคลังมีแต่พาร์ทอ่าน แต่พาร์ทฟังคือ 100 คะแนนจาก 300
ถ้าปล่อยให้แย่งที่กับพาร์ทอ่านในโควตา 10 ข้อเดียวกัน จะได้ฝึกฟังวันละ 2-3 ข้อ
ซึ่งไม่พอจะขยับคะแนนพาร์ทที่ยังเป็นศูนย์

**ทำไมนับจำนวนครั้งที่กดฟัง**
ข้อสอบจริงเปิดเสียงครั้งเดียว ตอบถูกหลังฟังห้ารอบ ≠ พร้อมสอบ
ตัวเลขนี้คือสิ่งที่บอกว่าพร้อมจริงไหม ไม่ใช่เปอร์เซ็นต์ความแม่น
"""
from __future__ import annotations

import random

from django.db.models import Count
from django.utils import timezone

from .models import (
    ErrorCode, ErrorLog, ListeningAttempt, Question, QuestionStatus, Section,
)

# ฟังเกินกี่ครั้งถึงนับว่ายังไม่ทันความเร็วจริง
# ข้อสอบเปิดครั้งเดียว แต่ตอนฝึกให้ฟังซ้ำได้หนึ่งรอบโดยไม่ตำหนิ
EXAM_PLAYS = 1


def pool():
    """ข้อฟังที่พร้อมใช้จริง — ต้องมีทั้งบทเสียง เฉลย และตัวเลือก"""
    return (
        Question.objects
        .filter(section=Section.LISTENING, status=QuestionStatus.ACTIVE)
        .exclude(audio_script="")
        .annotate(n_options=Count("options"))
        .filter(n_options__gte=2)
    )


def pick_question(*, exclude_ids: list[int] | None = None, seed: int | None = None):
    """สุ่มข้อฟังหนึ่งข้อ เลี่ยงข้อที่เพิ่งทำไป"""
    qs = pool()
    if exclude_ids:
        remaining = qs.exclude(pk__in=exclude_ids)
        qs = remaining if remaining.exists() else qs   # ทำครบแล้ววนใหม่
    ids = list(qs.values_list("pk", flat=True))
    if not ids:
        return None
    return Question.objects.filter(pk=random.Random(seed).choice(ids)).first()


def check(question: Question, given: str) -> dict:
    """ตรวจคำตอบ — เทียบข้อความ ไม่ใช่ตัวอักษร ก-ง

    เฉลยของข้อฟังเก็บเป็นข้อความเต็มของตัวเลือกที่ถูก (ดู import_exams)
    """
    correct = question.options.filter(is_correct=True).first()
    answer = (correct.text if correct else question.answer_text) or ""
    return {
        "is_correct": bool(given) and given.strip() == answer.strip(),
        "given": given,
        "correct_answer": answer,
    }


def record_result(learner, question: Question, result: dict, plays: int = 1) -> None:
    """บันทึกผล — ใช้สาเหตุ SOUND เสมอ

    ผิดข้อฟังไม่ได้แปลว่าไม่รู้คำ ส่วนใหญ่คือรู้คำแต่จำเสียงไม่ได้
    ซึ่งแก้ด้วยการฟังซ้ำ ไม่ใช่ด้วยการท่องคำเพิ่ม — นี่คือใจความของ D8
    """
    ListeningAttempt.objects.create(
        learner=learner, question=question,
        is_correct=result["is_correct"], plays=max(1, plays),
    )

    if result["is_correct"]:
        ErrorLog.objects.filter(
            learner=learner, question=question, resolved_at__isnull=True,
        ).update(resolved_at=timezone.now())
        return

    ErrorLog.record(
        learner, ErrorCode.SOUND,
        label=(question.prompt_zh or question.answer_text)[:200],
        section=Section.LISTENING, question=question,
    )


def stats(learner) -> dict:
    """ตัวเลขที่บอกว่าพร้อมสอบพาร์ทฟังแค่ไหน

    'ถูกตั้งแต่ฟังรอบเดียว' คือตัวเลขที่ตรงกับห้องสอบจริง ส่วนความแม่นรวม
    มองโลกในแง่ดีเกินไปเสมอ ต้องแสดงคู่กันไม่ใช่แสดงตัวเดียว
    """
    rows = ListeningAttempt.objects.filter(learner=learner)
    total = rows.count()
    if not total:
        return {"total": 0, "correct": 0, "accuracy": None,
                "one_play_correct": 0, "exam_accuracy": None, "pool": pool().count()}
    correct = rows.filter(is_correct=True).count()
    one_play = rows.filter(is_correct=True, plays__lte=EXAM_PLAYS).count()
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100),
        "one_play_correct": one_play,
        "exam_accuracy": round(one_play / total * 100),
        "pool": pool().count(),
    }
