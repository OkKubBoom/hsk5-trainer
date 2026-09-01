"""สรุปรายสัปดาห์ — ตัวเลขที่ตอบว่า "สัปดาห์นี้ขยับไหม"

**ทำไมต้องเทียบกับสัปดาห์ก่อน ไม่ใช่แสดงตัวเลขเดี่ยว**
"ตอบไป 180 ข้อ" ไม่บอกอะไรเลยถ้าไม่รู้ว่าสัปดาห์ก่อนตอบไปเท่าไหร่
เจ้าของระบบต้องตัดสินใจว่าจะเข้าไปคุยกับน้องไหม ซึ่งต้องดูทิศทาง ไม่ใช่ระดับ

**ทำไมแยกสาเหตุที่ผิด ไม่ใช่แค่จำนวนที่ผิด**
นี่คือ D8 ทั้งดุ้น — ผิด 30 ข้อเพราะไม่รู้ศัพท์ กับผิด 30 ข้อเพราะไม่ทันเวลา
ต้องแก้คนละวิธีกันคนละเรื่อง สรุปที่บอกแค่ "ผิด 30 ข้อ" ทำให้แก้ผิดทาง
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .models import (
    AnswerRecord, Card, DrillSession, ErrorCode, ErrorLog, ListeningAttempt,
    LoginDay, MockExam, ReviewSession, Section, WordOrderAttempt,
)

DAYS = 7

SECTION_LABEL = {
    Section.LISTENING: "听力 ฟัง",
    Section.READING: "阅读 อ่าน",
    Section.WRITING: "书写 เขียน",
}


def _delta(now: int, before: int) -> dict:
    """เทียบสองสัปดาห์ — คืนทั้งตัวเลขและทิศทาง ให้เทมเพลตไม่ต้องคิดเอง"""
    diff = now - before
    return {
        "now": now, "before": before, "diff": diff,
        "direction": "up" if diff > 0 else ("down" if diff < 0 else "flat"),
    }


def _counts(learner, start, end) -> dict:
    """สิ่งที่ทำในช่วงวันที่กำหนด"""
    drills = DrillSession.objects.filter(
        learner=learner, started_at__date__gte=start, started_at__date__lte=end)
    answers = AnswerRecord.objects.filter(
        session__learner=learner,
        answered_at__date__gte=start, answered_at__date__lte=end)
    reviews = ReviewSession.objects.filter(
        learner=learner, started_at__date__gte=start, started_at__date__lte=end)
    listens = ListeningAttempt.objects.filter(
        learner=learner, created_at__date__gte=start, created_at__date__lte=end)
    orders = WordOrderAttempt.objects.filter(
        learner=learner, created_at__date__gte=start, created_at__date__lte=end)

    # ความแม่นต้องนับจากทุกอย่างที่นับเป็น "ข้อที่ตอบ" ไม่ใช่เฉพาะชุดฝึกรายวัน
    # ถ้านับคนละฐาน หน้าจอจะขึ้นว่า "ตอบ 2 ข้อ · แม่น 0%" ทั้งที่ตอบถูกทั้งสองข้อ
    answered = answers.count() + listens.count() + orders.count()
    correct = (answers.filter(is_correct=True).count()
               + listens.filter(is_correct=True).count()
               + orders.filter(is_correct=True).count())
    active_days = set(drills.values_list("started_at__date", flat=True))
    active_days |= set(reviews.values_list("started_at__date", flat=True))
    active_days |= set(listens.values_list("created_at__date", flat=True))
    active_days |= set(orders.values_list("created_at__date", flat=True))

    return {
        "days": len(active_days),
        "answered": answered,
        "drill_answered": answers.count(),
        "correct": correct,
        "accuracy": round(correct / answered * 100) if answered else None,
        "listening": listens.count(),
        "listening_one_play": listens.filter(is_correct=True, plays__lte=1).count(),
        "word_order": orders.count(),
        "reviews": reviews.count(),
        "mocks": MockExam.objects.filter(
            learner=learner, started_at__date__gte=start,
            started_at__date__lte=end, finished_at__isnull=False).count(),
        "logins": LoginDay.objects.filter(
            user=learner.user, date__gte=start, date__lte=end).count(),
    }


def _causes(learner, start, end) -> list[dict]:
    """สาเหตุที่ตอบผิดในสัปดาห์นี้ เรียงจากมากไปน้อย — หัวใจของ D8"""
    rows = (
        ErrorLog.objects
        .filter(learner=learner, last_seen_at__date__gte=start, last_seen_at__date__lte=end)
        .values("code").annotate(n=Count("id")).order_by("-n")
    )
    labels = dict(ErrorCode.choices)
    total = sum(r["n"] for r in rows) or 1
    return [
        {"code": r["code"], "label": labels.get(r["code"], r["code"]),
         "count": r["n"], "percent": round(r["n"] / total * 100)}
        for r in rows
    ]


def _sections(learner, start, end) -> list[dict]:
    """พาร์ทไหนพลาดบ่อยที่สุดในสัปดาห์นี้"""
    rows = (
        ErrorLog.objects
        .filter(learner=learner, last_seen_at__date__gte=start, last_seen_at__date__lte=end)
        .exclude(section="")
        .values("section").annotate(n=Count("id")).order_by("-n")
    )
    return [{"section": r["section"],
             "label": SECTION_LABEL.get(r["section"], r["section"]),
             "count": r["n"]} for r in rows]


def _advice(counts, prev, causes, backlog, days_left) -> list[str]:
    """ข้อเสนอที่มาจากตัวเลขบนหน้าเดียวกัน ไม่ใช่คำแนะนำลอยๆ

    ทุกบรรทัดต้องอ้างตัวเลขที่ผู้อ่านเห็นอยู่ ไม่งั้นเป็นแค่กำลังใจ
    ซึ่งเจ้าของระบบเอาไปตัดสินใจอะไรไม่ได้
    """
    out = []
    if counts["days"] == 0:
        out.append("สัปดาห์นี้ยังไม่ได้แตะระบบเลย — เรื่องอื่นรอได้ เรื่องนี้รอไม่ได้")
        return out

    if counts["days"] < prev["days"]:
        out.append(
            f"ทำน้อยลงจากสัปดาห์ก่อน {prev['days']} วัน เหลือ {counts['days']} วัน "
            "— ความสม่ำเสมอสำคัญกว่าปริมาณต่อวัน"
        )
    if backlog > 0:
        out.append(
            f"ของค้างทบทวน {backlog} ใบ — เคลียร์ให้หมดก่อนเรียนคำใหม่ "
            "ไม่งั้นจะบวมจนเลิกกลางคัน"
        )
    if causes:
        top = causes[0]
        tip = {
            ErrorCode.SOUND: "เปิดหน้าฝึกฟังวันละ 10 ข้อ การท่องศัพท์เพิ่มไม่ช่วยเรื่องนี้",
            ErrorCode.TOO_SLOW: "รู้คำตอบแต่ไม่ทัน — ฝึกจับเวลา ไม่ใช่เรียนคำเพิ่ม",
            ErrorCode.VOCAB: "ยังไม่รู้ศัพท์จริงๆ — เพิ่มเวลาที่หน้าฝึกจำคำศัพท์",
            ErrorCode.MEANING: "รู้คำแต่เลือกผิดในบริบท — ดูตัวอย่างประโยคของคำนั้นทุกครั้ง",
            ErrorCode.STRUCTURE: "จับโครงประโยคผิด — ฝึกเรียงคำจะตรงจุดที่สุด",
            ErrorCode.CARELESS: "อ่านโจทย์ไม่ครบ — ช้าลงอีกนิดคุ้มกว่าตอบเร็วแล้วผิด",
        }.get(top["code"], "")
        out.append(f"สาเหตุที่ผิดมากที่สุดคือ “{top['label']}” ({top['percent']}%) — {tip}")
    if counts["listening"] == 0:
        out.append("สัปดาห์นี้ไม่ได้ฝึกฟังเลย — พาร์ทฟังคือ 100 คะแนนจาก 300")
    if days_left is not None and days_left <= 21 and counts["mocks"] == 0:
        out.append(
            f"เหลือ {days_left} วันแล้วแต่ยังไม่ได้จำลองสอบสัปดาห์นี้ "
            "— ต้องรู้ว่าทำทันเวลาไหมก่อนเข้าห้องสอบจริง"
        )
    return out


def summary(learner, today=None) -> dict:
    """สรุปเจ็ดวันล่าสุด เทียบกับเจ็ดวันก่อนหน้า"""
    today = today or timezone.localdate()
    start = today - timedelta(days=DAYS - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=DAYS - 1)

    counts = _counts(learner, start, today)
    prev = _counts(learner, prev_start, prev_end)
    causes = _causes(learner, start, today)
    backlog = Card.objects.filter(
        learner=learner, due_at__date__lte=today).exclude(state="suspended").count()
    days_left = (learner.target_exam_date - today).days if learner.target_exam_date else None

    return {
        "learner": learner,
        "start": start, "end": today,
        "prev_start": prev_start, "prev_end": prev_end,
        "counts": counts, "prev": prev,
        "compare": {
            "days": _delta(counts["days"], prev["days"]),
            "answered": _delta(counts["answered"], prev["answered"]),
            "accuracy": _delta(counts["accuracy"] or 0, prev["accuracy"] or 0),
            "listening": _delta(counts["listening"], prev["listening"]),
        },
        "causes": causes,
        "sections": _sections(learner, start, today),
        "backlog": backlog,
        "days_left": days_left,
        "advice": _advice(counts, prev, causes, backlog, days_left),
    }
