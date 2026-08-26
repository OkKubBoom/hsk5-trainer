"""ความคืบหน้าของผู้เรียนในกลุ่ม — เทียบ "ความพยายาม" ไม่ใช่ "คะแนน"

ตั้งใจไม่โชว์ความแม่นของคนอื่น เพราะเทียบกันไม่ได้จริง: คนที่การ์ดง่ายกว่า
ย่อมแม่นกว่าโดยอัตโนมัติ ตัวเลขที่เอามาเทียบได้อย่างเป็นธรรมคือสิ่งที่
ตัวเองควบคุมได้ — ทำหรือไม่ทำ ทำติดกันกี่วัน ตอบไปกี่ข้อ
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import DrillSession, LearnerProfile

CALENDAR_DAYS = 30


def _finished_dates(learner) -> set:
    return set(
        DrillSession.objects
        .filter(learner=learner, finished_at__isnull=False)
        .values_list("started_at__date", flat=True)
    )


def streak(dates: set, today=None) -> int:
    """จำนวนวันที่ทำติดต่อกัน — วันนี้ยังไม่ทำไม่ถือว่าขาด ถ้าเมื่อวานทำ"""
    today = today or timezone.localdate()
    if not dates:
        return 0
    start = today if today in dates else today - timedelta(days=1)
    if start not in dates:
        return 0
    count = 0
    day = start
    while day in dates:
        count += 1
        day -= timedelta(days=1)
    return count


def group_progress(today=None) -> list[dict]:
    """สรุปของผู้เรียนทุกคนในระบบ เรียงตามคนที่ยังไม่ทำวันนี้ขึ้นก่อน

    เรียงแบบนี้เพราะหน้านี้มีไว้ให้เห็นว่า "ใครยังไม่ทำ" ไม่ใช่ "ใครเก่งกว่า"
    ไม่มีอันดับ 1-2-3 โดยตั้งใจ
    """
    today = today or timezone.localdate()
    window = [today - timedelta(days=i) for i in range(CALENDAR_DAYS - 1, -1, -1)]

    rows = []
    for learner in LearnerProfile.objects.select_related("user").order_by("user__first_name", "user__username"):
        dates = _finished_dates(learner)
        sessions = DrillSession.objects.filter(learner=learner)
        today_session = sessions.filter(started_at__date=today).first()

        rows.append({
            "learner": learner,
            "name": learner.user.first_name or learner.user.username,
            "initial": (learner.user.first_name or learner.user.username)[:1],
            "done_today": bool(today_session and today_session.finished_at),
            "in_progress_today": bool(today_session and not today_session.finished_at),
            "answered_today": today_session.answered if today_session else 0,
            "streak": streak(dates, today),
            "sessions_done": len(dates),
            "answered_total": sum(s.answered for s in sessions),
            "days_to_exam": (learner.target_exam_date - today).days,
            "calendar": [{"date": d, "done": d in dates} for d in window],
            "active_days": sum(1 for d in window if d in dates),
        })

    rows.sort(key=lambda r: (r["done_today"], -r["streak"]))
    return rows
