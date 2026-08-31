"""ข้อสอบจำลอง — จับเวลา ส่งทีเดียวตอนจบ ไม่เฉลยระหว่างทาง

ต่างจากชุดฝึกรายวันโดยตั้งใจ:
  ชุดฝึก  = เฉลยทันทีทีละข้อ  → จุดประสงค์คือ *เรียนรู้จากความผิด*
  จำลองสอบ = กั๊กเฉลยไว้ท้ายสุด → จุดประสงค์คือ *วัดว่าตอนนี้ทำได้เท่าไร*

ถ้าเฉลยระหว่างทาง คะแนนที่ได้จะไม่สะท้อนความสามารถจริง เพราะข้อหลังๆ
ได้เปรียบจากการเห็นเฉลยข้อก่อน — และ CLAUDE.md ระบุว่าให้ทำสัปดาห์ละครั้ง
ไม่ใช่ทุกวัน เพราะทำถี่เกินไปคือการวัดความล้า ไม่ใช่วัดความรู้
"""
from __future__ import annotations

import random

from django.db.models import Q
from django.utils import timezone

from . import diagnose
from .models import (
    ErrorCode, ErrorLog, MockExam, Question, QuestionStatus, Section,
)

# โครงพาร์ทอ่านจริงของ HSK5 2.0 — ข้อ 46-90
READING_BLUEPRINT = [
    {"key": "cloze", "label": "เลือกคำเติมช่องว่าง", "count": 15,
     "filter": Q(qtype="synonym_cloze")},
    {"key": "match", "label": "เลือกข้อที่ตรงกับเนื้อหา", "count": 10,
     "filter": Q(qtype="reading_mc", group__isnull=True)},
    {"key": "passage", "label": "อ่านบทความแล้วตอบคำถาม", "count": 20,
     "filter": Q(qtype="reading_mc", group__isnull=False)},
]

READING_MINUTES = 45
RECENT_EXAMS_TO_AVOID = 2


def _recently_used(learner, limit: int = RECENT_EXAMS_TO_AVOID) -> set[int]:
    """ข้อที่เพิ่งเจอในการสอบจำลองครั้งก่อนๆ — เลี่ยงไว้เพื่อไม่ให้จำคำตอบได้

    ถ้าเจอชุดเดิมซ้ำ คะแนนจะสูงขึ้นเพราะจำได้ ไม่ใช่เพราะเก่งขึ้น
    ซึ่งทำให้กราฟความคืบหน้าโกหกตัวเอง
    """
    used: set[int] = set()
    for exam in MockExam.objects.filter(learner=learner).order_by("-started_at")[:limit]:
        used.update(exam.queue or [])
    return used


def _pick_by_group(pool: list, count: int, rng: random.Random) -> list[int]:
    """หยิบทั้งบทอ่าน ไม่ใช่หยิบทีละข้อ

    ของเดิมสุ่มรายข้อ ทำให้ชุด 45 ข้อกระจายอยู่ใน 30 บทอ่าน (1.13 ข้อต่อบท)
    ทั้งที่ข้อสอบจริงมีราว 4 ข้อต่อบท ผู้เรียนจึงต้องอ่านหนักกว่าของจริงเกือบสามเท่า
    ในเวลาเท่ากัน — แล้วสรุปว่าตัวเองอ่านช้า ทั้งที่โจทย์ต่างหากที่ผิดรูป

    รับ list ของ (pk, group_id) แล้วคืน pk ที่จัดกลุ่มแล้ว
    """
    by_group: dict[int, list[int]] = {}
    solo: list[int] = []
    for pk, gid in pool:
        if gid:
            by_group.setdefault(gid, []).append(pk)
        else:
            solo.append(pk)

    groups = list(by_group.values())
    rng.shuffle(groups)
    rng.shuffle(solo)

    chosen: list[int] = []
    for group in groups:
        if len(chosen) >= count:
            break
        # ยอมเกินเป้าเล็กน้อยเพื่อรักษาบทอ่านให้ครบ ดีกว่าตัดกลางบท
        chosen.extend(group)

    # บทอ่านไม่พอ ค่อยเติมด้วยข้อเดี่ยว
    for pk in solo:
        if len(chosen) >= count:
            break
        chosen.append(pk)

    return chosen[:count] if len(chosen) > count else chosen


def build_reading_set(learner, *, seed: int | None = None) -> list[int]:
    """สุ่มชุดข้อสอบพาร์ทอ่านตามสัดส่วนจริง และเปลี่ยนไปทุกครั้งที่สอบ"""
    rng = random.Random(seed)
    avoid = _recently_used(learner)
    picked: list[int] = []

    for part in READING_BLUEPRINT:
        rows = list(
            Question.objects
            .filter(part["filter"], status=QuestionStatus.ACTIVE)
            .exclude(pk__in=picked)
            .values_list("pk", "group_id")
        )
        fresh = [r for r in rows if r[0] not in avoid]
        chosen = _pick_by_group(fresh, part["count"], rng)
        if len(chosen) < part["count"]:
            # ของใหม่ไม่พอ ค่อยยอมใช้ของเก่า — ขนาดชุดต้องคงที่เสมอ
            leftover = [r for r in rows if r[0] not in chosen]
            chosen += _pick_by_group(leftover, part["count"] - len(chosen), rng)
        picked.extend(chosen)

    return picked


def start(learner, *, seed: int | None = None) -> MockExam | None:
    """เริ่มสอบจำลองพาร์ทอ่าน — ถ้ามีชุดที่ยังทำค้างอยู่ให้ทำต่อ ไม่สร้างใหม่"""
    running = MockExam.objects.filter(
        learner=learner, started_at__isnull=False, finished_at__isnull=True,
    ).order_by("-started_at").first()
    if running:
        return running

    queue = build_reading_set(learner, seed=seed)
    if not queue:
        # คลังข้อสอบไม่พอ — สร้างชุดเปล่าแล้วหน้าทำข้อสอบจะพังตอนหยิบข้อแรก
        # คืน None ให้ view บอกผู้ใช้ตรงๆ ดีกว่าปล่อยให้เจอหน้า error
        return None
    return MockExam.objects.create(
        learner=learner, taken_on=timezone.localdate(), section=Section.READING,
        queue=queue, answers={}, flagged=[], started_at=timezone.now(),
        time_limit_minutes=READING_MINUTES, is_timed=True,
        paper_ref="สุ่มจากคลังข้อสอบจริง",
    )


def save_answer(exam: MockExam, question_id: int, given: str) -> None:
    """บันทึกทุกครั้งที่เลือก — ปิดเบราว์เซอร์กลางคันแล้วกลับมาทำต่อได้"""
    answers = dict(exam.answers or {})
    answers[str(question_id)] = given[:400]
    exam.answers = answers
    exam.save(update_fields=["answers", "updated_at"])


def toggle_flag(exam: MockExam, question_id: int) -> bool:
    flagged = list(exam.flagged or [])
    if question_id in flagged:
        flagged.remove(question_id)
        on = False
    else:
        flagged.append(question_id)
        on = True
    exam.flagged = flagged
    exam.save(update_fields=["flagged", "updated_at"])
    return on


def grade(exam: MockExam, *, auto: bool = False) -> MockExam:
    """ตรวจทั้งชุด แปลงเป็นคะแนนเทียบสเกลข้อสอบจริง แล้วบันทึกข้อที่ผิด"""
    answers = exam.answers or {}
    questions = {q.pk: q for q in Question.objects.filter(pk__in=exam.queue or []).prefetch_related("options")}

    correct = 0
    for qid in exam.queue or []:
        question = questions.get(qid)
        if not question:
            continue
        given = (answers.get(str(qid)) or "").strip()
        right = next((o.text for o in question.options.all() if o.is_correct), question.answer_text)
        if given and given == (right or "").strip():
            correct += 1
            # ตอบถูกในข้อสอบจำลอง = แก้ได้แล้ว ต้องปิดบันทึกข้อผิดเดิมด้วย
            ErrorLog.objects.filter(
                learner=exam.learner, question=question, resolved_at__isnull=True,
            ).update(resolved_at=timezone.now())
        elif given:
            # ตอบผิด (ไม่ใช่ไม่ได้ตอบ) → เข้าคิวตามตื้อในชุดฝึกวันถัดไป
            # ไม่จับเวลารายข้อในโหมดนี้ จึงส่ง elapsed_ms=0 แล้วให้เดาจากชนิดโจทย์
            ErrorLog.record(
                exam.learner, diagnose.code_for(question=question),
                label=(question.source_ref or question.prompt_zh[:60])[:200],
                section=question.section, question=question,
                vocab=question.vocab,
            )

    exam.correct_count = correct
    # พาร์ทอ่านของจริงเต็ม 100 คะแนนจาก 45 ข้อ
    exam.reading = round(correct / len(exam.queue or [1]) * 100) if exam.queue else 0
    exam.finished_at = timezone.now()
    exam.auto_submitted = auto
    exam.save(update_fields=[
        "correct_count", "reading", "finished_at", "auto_submitted", "updated_at",
    ])
    return exam


def stats(learner) -> dict:
    """สถิติการสอบจำลองของผู้เรียนคนนี้"""
    finished = list(
        MockExam.objects.filter(learner=learner, finished_at__isnull=False).order_by("-finished_at")
    )
    scores = [e.reading for e in finished]
    return {
        "times": len(finished),
        "best": max(scores) if scores else None,
        "latest": scores[0] if scores else None,
        "average": round(sum(scores) / len(scores)) if scores else None,
        "trend": (scores[0] - scores[1]) if len(scores) >= 2 else None,
        "history": finished[:20],
        "total_minutes": sum(e.minutes_used or 0 for e in finished),
    }


def question_states(exam: MockExam) -> list[dict]:
    """สถานะรายข้อสำหรับผังข้อ — ตอบแล้ว / ปักธง / ยังไม่ตอบ"""
    answers = exam.answers or {}
    flagged = set(exam.flagged or [])
    out = []
    for i, qid in enumerate(exam.queue or [], start=1):
        out.append({
            "number": i,
            "id": qid,
            "answered": str(qid) in answers,
            "flagged": qid in flagged,
        })
    return out
