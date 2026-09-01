"""วัดผลพาร์ทฟัง — จับเวลา ฟังครั้งเดียว ไม่เฉลยระหว่างทาง

**ต่างจากหน้าฝึกฟังอย่างไร และทำไมต้องมีทั้งสองอย่าง**
  /listen/       ฝึก   — ฟังซ้ำได้ เฉลยทันที เห็นบทหลังตอบ  → จุดประสงค์คือ *เรียนรู้*
  /listen/test/  วัด   — ฟังครั้งเดียว กั๊กเฉลยไว้ท้ายสุด      → จุดประสงค์คือ *รู้ว่าตอนนี้ทำได้เท่าไร*

หน้าฝึกให้ตัวเลขที่มองโลกในแง่ดีเกินไปเสมอ เพราะฟังซ้ำได้ไม่จำกัด
ตัวเลขที่เอาไปตัดสินใจว่าสมัครสอบรอบไหน ต้องมาจากเงื่อนไขเดียวกับห้องสอบ

**เรื่องขนาดชุด — ต้องพูดให้ตรง**
ชุด 5 ข้อ ดีสำหรับ *นิสัยรายวัน* แต่ไม่ใช่เครื่องมือวัด
หนึ่งข้อ = 20% ของคะแนน เดาถูกข้อเดียวเลขเด้ง 20 จุด
ชุดเล็กจึงติดป้ายว่า "ซ้อม" ไม่ใช่ "วัด" และมีเฉพาะชุด 45 ข้อที่เรียกว่าวัดผลได้
"""
from __future__ import annotations

import random

from django.utils import timezone

from . import listen_drill
from .models import (
    ErrorCode, ErrorLog, ListeningAttempt, MockExam, Question, Section,
)

# ข้อสอบจริง 45 ข้อ ~30 นาที ≈ 40 วินาทีต่อข้อ ใช้อัตราเดียวกันทุกขนาด
SECONDS_PER_QUESTION = 40

SIZES = [
    {"count": 5, "label": "ซ้อมสั้น", "kind": "practice",
     "note": "พอสำหรับทำทุกวัน แต่เล็กเกินกว่าจะเชื่อเป็นคะแนน"},
    {"count": 10, "label": "ซ้อมกลาง", "kind": "practice",
     "note": "เห็นแนวโน้มได้บ้าง ยังไม่ใช่ตัวเลขที่เอาไปตัดสินใจ"},
    {"count": 45, "label": "เต็มพาร์ท", "kind": "measure",
     "note": "เท่าข้อสอบจริง — ตัวเลขจากชุดนี้เท่านั้นที่เอาไปเทียบกับ 100 คะแนนได้"},
]

RECENT_EXAMS_TO_AVOID = 2


def size_options() -> list[dict]:
    """ตัวเลือกขนาดชุด พร้อมเวลาที่คำนวณจากอัตราเดียวกับข้อสอบจริง"""
    available = listen_drill.pool().count()
    return [
        {**s,
         "minutes": max(3, round(s["count"] * SECONDS_PER_QUESTION / 60)),
         "enough": available >= s["count"]}
        for s in SIZES
    ]


def _recently_used(learner, limit: int = RECENT_EXAMS_TO_AVOID) -> set[int]:
    """ข้อที่เพิ่งเจอ — เจอชุดเดิมซ้ำแล้วคะแนนสูงขึ้นเพราะจำได้ ไม่ใช่เพราะเก่งขึ้น"""
    used = set()
    for exam in MockExam.objects.filter(
        learner=learner, section=Section.LISTENING, finished_at__isnull=False,
    ).order_by("-finished_at")[:limit]:
        used |= set(exam.queue or [])
    return used


def start(learner, count: int, *, seed: int | None = None) -> MockExam | None:
    """เริ่มชุดวัดผล — มีชุดค้างอยู่ให้ทำต่อ ไม่สร้างใหม่"""
    running = MockExam.objects.filter(
        learner=learner, section=Section.LISTENING,
        started_at__isnull=False, finished_at__isnull=True,
    ).order_by("-started_at").first()
    if running:
        return running

    ids = list(listen_drill.pool().values_list("pk", flat=True))
    if len(ids) < count:
        return None

    rng = random.Random(seed)
    avoid = _recently_used(learner)
    fresh = [i for i in ids if i not in avoid]
    rng.shuffle(fresh)
    queue = fresh[:count]
    if len(queue) < count:
        # ของใหม่ไม่พอ ค่อยยอมใช้ของเก่า — ขนาดชุดต้องคงที่เสมอ
        leftover = [i for i in ids if i not in queue]
        rng.shuffle(leftover)
        queue += leftover[: count - len(queue)]

    return MockExam.objects.create(
        learner=learner, taken_on=timezone.localdate(), section=Section.LISTENING,
        queue=queue, answers={}, flagged=[], started_at=timezone.now(),
        time_limit_minutes=max(3, round(count * SECONDS_PER_QUESTION / 60)),
        is_timed=True, paper_ref="สุ่มจากคลังข้อสอบจริง",
    )


def position(exam: MockExam) -> int:
    """ข้อที่กำลังทำ — นับจากจำนวนที่ตอบไปแล้ว

    ไม่เก็บตัวชี้แยก เพราะจะเพี้ยนกับ answers ได้เมื่อผู้เรียนกดรีเฟรช
    """
    return len(exam.answers or {})


def current(exam: MockExam) -> Question | None:
    i = position(exam)
    queue = exam.queue or []
    if i >= len(queue):
        return None
    return Question.objects.filter(pk=queue[i]).prefetch_related("options").first()


def save_answer(exam: MockExam, question_id: int, given: str) -> None:
    """บันทึกทันทีทีละข้อ — ปิดเบราว์เซอร์กลางคันแล้วกลับมาทำต่อได้

    ตอบแล้วย้อนกลับไม่ได้ เหมือนห้องสอบจริง จึงเขียนทับของเดิมไม่ได้
    """
    answers = dict(exam.answers or {})
    answers.setdefault(str(question_id), (given or "")[:400])
    exam.answers = answers
    exam.save(update_fields=["answers", "updated_at"])


def is_expired(exam: MockExam) -> bool:
    if not exam.is_timed or not exam.started_at:
        return False
    used = (timezone.now() - exam.started_at).total_seconds() / 60
    return used > exam.time_limit_minutes


def submit(exam: MockExam, *, auto: bool = False) -> MockExam:
    """ตรวจทั้งชุดตอนจบ แล้วบันทึกทุกข้อลงประวัติการฝึกฟังด้วย

    บันทึกลง ListeningAttempt ด้วย plays=1 เพราะชุดนี้ฟังได้ครั้งเดียวจริง
    ตัวเลข "ถูกตั้งแต่ฟังรอบเดียว" ในหน้าฝึกจึงรวมผลจากชุดวัดผลอย่างถูกต้อง
    """
    if exam.finished_at:
        return exam

    answers = exam.answers or {}
    questions = {q.pk: q for q in
                 Question.objects.filter(pk__in=exam.queue or []).prefetch_related("options")}
    correct = 0

    for qid in exam.queue or []:
        question = questions.get(qid)
        if not question:
            continue
        given = (answers.get(str(qid)) or "").strip()
        result = listen_drill.check(question, given)

        ListeningAttempt.objects.create(
            learner=exam.learner, question=question,
            is_correct=result["is_correct"], plays=1,
        )
        if result["is_correct"]:
            correct += 1
            ErrorLog.objects.filter(
                learner=exam.learner, question=question, resolved_at__isnull=True,
            ).update(resolved_at=timezone.now())
        elif given:
            # ไม่ได้ตอบ (หมดเวลา) ไม่ใช่ "ตอบผิด" — ไม่ควรถูกตีความว่าฟังไม่ออก
            ErrorLog.record(
                exam.learner, ErrorCode.SOUND,
                label=(question.source_ref or question.prompt_zh[:60])[:200],
                section=Section.LISTENING, question=question,
            )

    exam.correct_count = correct
    # พาร์ทฟังของจริงเต็ม 100 คะแนนจาก 45 ข้อ
    exam.listening = round(correct / len(exam.queue or [1]) * 100) if exam.queue else 0
    exam.finished_at = timezone.now()
    exam.auto_submitted = auto
    exam.save(update_fields=[
        "correct_count", "listening", "finished_at", "auto_submitted", "updated_at",
    ])
    return exam


def review(exam: MockExam) -> list[dict]:
    """ผลรายข้อสำหรับหน้าเฉลย — พร้อมบทที่ได้ยิน"""
    from . import listen_explain

    answers = exam.answers or {}
    questions = {q.pk: q for q in
                 Question.objects.filter(pk__in=exam.queue or []).prefetch_related("options")}
    rows = []
    for n, qid in enumerate(exam.queue or [], start=1):
        question = questions.get(qid)
        if not question:
            continue
        given = (answers.get(str(qid)) or "").strip()
        result = listen_drill.check(question, given)
        rows.append({
            "n": n, "question": question, "given": given,
            "is_correct": result["is_correct"],
            "answer": result["correct_answer"],
            "skipped": not given,
            "lx": listen_explain.explain(question),
        })
    return rows


def history(learner) -> dict:
    """ผลย้อนหลังเฉพาะชุดเต็มพาร์ท — ชุดสั้นไม่นับเป็นคะแนน

    ถ้าเอาชุด 5 ข้อมาปนในกราฟแนวโน้ม เส้นจะเด้งจนอ่านไม่ได้
    และคนอ่านจะเข้าใจว่าคะแนนขึ้นลงจริง ทั้งที่เป็นความบังเอิญของชุดเล็ก
    """
    done = list(
        MockExam.objects.filter(
            learner=learner, section=Section.LISTENING, finished_at__isnull=False)
        .order_by("-finished_at")
    )
    full = [e for e in done if len(e.queue or []) >= 45]
    scores = [e.listening for e in full]
    return {
        "all": done[:20],
        "full_times": len(full),
        "best": max(scores) if scores else None,
        "latest": scores[0] if scores else None,
        "trend": (scores[0] - scores[1]) if len(scores) >= 2 else None,
    }
