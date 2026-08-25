"""ตัวจัดตารางทบทวน — SM-2 ที่รู้จักวันสอบ (scheduler เวอร์ชัน "sm2d-1")

ทำไมไม่ใช้ SM-2 ตรงๆ: SM-2 ออกแบบมาสำหรับการเรียนที่ไม่มีวันสิ้นสุด
แต่ที่นี่มีเส้นตายตายตัว สองอย่างจึงต่างออกไป

  1. ไม่นัดทบทวนหลังวันสอบ — การ์ดที่ระบบบอกว่า "เจอกันอีกที 90 วัน" ทั้งที่เหลือ 40 วัน
     เท่ากับทิ้งคำนั้นไปเลย จึงบีบระยะห่างไม่ให้เกินสัดส่วนของเวลาที่เหลือ

  2. ช่วง freeze ก่อนสอบต้องให้ทุกใบผ่านสายตาอย่างน้อยครั้งหนึ่ง

ตรรกะทั้งหมดอยู่ในไฟล์นี้ไฟล์เดียว ห้ามกระจายเข้า view (ดู CLAUDE.md ข้อ 11)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from django.conf import settings
from django.utils import timezone

from .models import Card, CardState, Rating, ReviewLog

SCHEDULER_VERSION = "sm2d-1"

MIN_EASE = 1.3
MAX_EASE = 2.8
LEARNING_STEPS_MINUTES = (10, 1440)   # 10 นาที แล้ว 1 วัน
DEADLINE_RATIO = 0.6                  # ระยะห่างสูงสุด = 60% ของวันที่เหลือถึงสอบ


def target_exam_date(learner=None) -> date:
    if learner is not None and getattr(learner, "target_exam_date", None):
        return learner.target_exam_date
    return date.fromisoformat(settings.TARGET_EXAM_DATE)


def days_to_exam(learner=None, today: date | None = None) -> int:
    return (target_exam_date(learner) - (today or timezone.localdate())).days


def in_freeze(learner=None, today: date | None = None) -> bool:
    """ช่วงก่อนสอบที่หยุดเรียนคำใหม่ทั้งหมด"""
    return days_to_exam(learner, today) <= settings.SRS_FREEZE_DAYS


def cap_interval(interval_days: float, learner=None, today: date | None = None) -> float:
    """บีบระยะห่างไม่ให้ยาวจนเลยวันสอบ

    เหลือ 100 วัน → นัดได้ไกลสุด 60 วัน
    เหลือ 10 วัน  → นัดได้ไกลสุด 6 วัน
    เลยวันสอบแล้ว → 1 วัน (ไม่ตกไปเป็น 0 หรือติดลบ)
    """
    left = days_to_exam(learner, today)
    if left <= 1:
        return 1.0
    return max(1.0, min(interval_days, left * DEADLINE_RATIO))


def next_interval(card: Card, rating: int, learner=None, today: date | None = None) -> float:
    """คำนวณระยะห่างครั้งถัดไปเป็นวัน (ยังไม่บันทึก)"""
    if rating == Rating.AGAIN:
        return 0.0

    ease = card.ease or 2.5
    prev = card.interval_days or 0.0

    if prev < 1:
        base = 1.0
    elif prev < 3:
        base = 3.0
    else:
        base = prev * ease

    if rating == Rating.HARD:
        base = max(1.0, (prev or 1.0) * 1.2)
    elif rating == Rating.EASY:
        base *= 1.3

    return cap_interval(base, learner, today)


def adjust_ease(ease: float, rating: int) -> float:
    delta = {Rating.AGAIN: -0.20, Rating.HARD: -0.15, Rating.GOOD: 0.0, Rating.EASY: 0.10}[rating]
    return max(MIN_EASE, min(MAX_EASE, (ease or 2.5) + delta))


def review(card: Card, rating: int, *, elapsed_ms: int = 0, now: datetime | None = None) -> ReviewLog:
    """บันทึกการทบทวนหนึ่งครั้งและนัดครั้งถัดไป

    เป็นทางเดียวที่ได้รับอนุญาตให้แก้ค่า due_at / interval_days / ease
    ที่อื่นห้ามแตะโดยตรง มิฉะนั้นตารางทบทวนจะเพี้ยนแบบเงียบ
    """
    now = now or timezone.now()
    learner = card.learner
    prev_interval = card.interval_days or 0.0

    new_interval = next_interval(card, rating, learner, now.date())
    card.ease = adjust_ease(card.ease, rating)
    card.reps += 1
    card.last_reviewed_at = now

    if rating == Rating.AGAIN:
        card.lapses += 1
        card.interval_days = 0.0
        card.state = CardState.LAPSED if card.reps > 1 else CardState.LEARNING
        card.due_at = now + timedelta(minutes=LEARNING_STEPS_MINUTES[0])
    else:
        card.interval_days = new_interval
        card.state = CardState.REVIEW if new_interval >= 1 else CardState.LEARNING
        card.due_at = now + timedelta(days=new_interval)

    card.save(update_fields=[
        "ease", "reps", "lapses", "interval_days", "state", "due_at",
        "last_reviewed_at", "updated_at",
    ])

    return ReviewLog.objects.create(
        card=card,
        rating=rating,
        elapsed_ms=elapsed_ms,
        prev_interval_days=prev_interval,
        new_interval_days=card.interval_days,
        scheduler_version=SCHEDULER_VERSION,
    )


def due_queryset(learner, now: datetime | None = None):
    """การ์ดที่ถึงกำหนดทบทวน เรียงจากที่ค้างนานที่สุดก่อน"""
    now = now or timezone.now()
    return (
        Card.objects
        .filter(learner=learner, due_at__lte=now)
        .exclude(state__in=[CardState.NEW, CardState.SUSPENDED])
        .select_related("vocab")
        .order_by("due_at")
    )


def new_queryset(learner):
    """การ์ดที่ยังไม่เคยเรียน เรียงตามความถี่ของคำ (คำที่เจอบ่อยมาก่อน)"""
    return (
        Card.objects
        .filter(learner=learner, state=CardState.NEW)
        .select_related("vocab")
        .order_by("vocab__frequency_rank", "vocab__hanzi")
    )


def new_quota_today(learner, now: datetime | None = None) -> int:
    """โควตาคำใหม่วันนี้ หลังผ่านตัวคุมโหลดและช่วง freeze

    ตัวคุมโหลดคือกฎที่กันไม่ให้เลิกกลางคัน: การ์ดค้างพอกจนเปิดแอปแล้วท้อ
    คือสาเหตุอันดับหนึ่งที่คนหยุดใช้ระบบทบทวน ระบบต้องเบรกเอง
    ไม่ใช่รอให้ผู้เรียนมีวินัยพอที่จะเบรกตัวเอง
    """
    today = (now or timezone.now()).date()
    if in_freeze(learner, today):
        return 0
    backlog = due_queryset(learner, now).count()
    if backlog >= settings.SRS_BACKLOG_CEILING:
        return 0
    if backlog >= settings.SRS_BACKLOG_CEILING * 0.7:
        return max(0, learner.new_words_per_day // 2)
    return learner.new_words_per_day
