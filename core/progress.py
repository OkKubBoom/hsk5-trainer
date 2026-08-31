"""ความคืบหน้าของผู้เรียนในกลุ่ม — เทียบ "ความพยายาม" ไม่ใช่ "คะแนน"

ตั้งใจไม่โชว์ความแม่นของคนอื่น เพราะเทียบกันไม่ได้จริง: คนที่การ์ดง่ายกว่า
ย่อมแม่นกว่าโดยอัตโนมัติ ตัวเลขที่เอามาเทียบได้อย่างเป็นธรรมคือสิ่งที่
ตัวเองควบคุมได้ — ทำหรือไม่ทำ ทำติดกันกี่วัน ตอบไปกี่ข้อ

หน้านี้บอกด้วยว่าแต่ละคน *ทำอะไร* ไม่ใช่แค่ "ทำ/ไม่ทำ"
เพราะวันที่ทวนคำศัพท์อย่างเดียวกับวันที่ไม่ได้แตะระบบเลย ไม่เหมือนกัน
แต่ปฏิทินเดิมแสดงเป็นสีเทาเหมือนกันทั้งคู่
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import (
    DrillSession, LearnerProfile, LoginDay, MockExam, PlacementTest, ReviewSession,
    WordOrderAttempt,
)

CALENDAR_DAYS = 30

# ชนิดกิจกรรมที่ระบบเก็บได้จริง เรียงตามน้ำหนักที่ให้กับการสอบ
ACTIVITY_LABEL = {
    "drill": "ชุดฝึกวันนี้",
    "review": "ฝึกจำคำศัพท์",
    "mock": "จำลองสอบ",
    "placement": "แบบวัดระดับ",
    "word_order": "ฝึกเรียงคำ",
}


def _drill_dates(learner) -> set:
    """วันที่ทำ *ชุดฝึกรายวันจบ* — ใช้นับ streak เท่านั้น

    ไม่รวมกิจกรรมอื่นโดยตั้งใจ เพราะ streak คือคำสัญญาว่า "ทำชุดหลักทุกวัน"
    ถ้านับรวมทุกอย่าง การเปิดทวนคำศัพท์ 2 นาทีจะรักษา streak ไว้ได้
    ซึ่งทำให้ตัวเลขไม่ได้หมายถึงอะไรอีกต่อไป
    """
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


def _activity_by_date(learner, window: list) -> dict:
    """สิ่งที่ทำในแต่ละวัน แยกตามชนิดกิจกรรม

    เก็บเป็น dict ของวันที่ เพื่อให้เทมเพลตหยิบไปแสดงในปฏิทินได้โดยไม่ต้องคิวรีซ้ำ
    """
    first = window[0]
    by_date = {d: {"drill": 0, "review": 0, "mock": 0, "word_order": 0, "answered": 0}
               for d in window}

    for s in DrillSession.objects.filter(learner=learner, started_at__date__gte=first):
        day = by_date.get(s.started_at.date())
        if day is not None and s.finished_at:
            day["drill"] += 1
            day["answered"] += s.answered

    for s in ReviewSession.objects.filter(learner=learner, started_at__date__gte=first, answered__gte=1):
        day = by_date.get(s.started_at.date())
        if day is not None:
            day["review"] += 1
            day["answered"] += s.answered

    for e in MockExam.objects.filter(learner=learner, started_at__date__gte=first, finished_at__isnull=False):
        day = by_date.get(e.started_at.date())
        if day is not None:
            day["mock"] += 1

    for a in WordOrderAttempt.objects.filter(learner=learner, created_at__date__gte=first):
        day = by_date.get(a.created_at.date())
        if day is not None:
            day["word_order"] += 1
            day["answered"] += 1

    return by_date


def _day_label(date, act: dict) -> str:
    """ข้อความที่ขึ้นตอนชี้/แตะช่องปฏิทิน — ต้องบอกวันที่เสมอ

    เดิมใช้ title ของ HTML ซึ่งบนแท็บเล็ตไม่ขึ้นเลยเพราะไม่มีการชี้เมาส์
    """
    parts = []
    if act["drill"]:
        parts.append(f"ชุดฝึกวันนี้ {act['drill']} ชุด")
    if act["review"]:
        parts.append(f"ฝึกจำคำศัพท์ {act['review']} รอบ")
    if act["mock"]:
        parts.append(f"จำลองสอบ {act['mock']} ครั้ง")
    if act["word_order"]:
        parts.append(f"ฝึกเรียงคำ {act['word_order']} ข้อ")
    if not parts:
        return "เข้าระบบแต่ไม่ได้ทำอะไร" if act.get("login") else "ไม่ได้ทำอะไร"
    if act["answered"]:
        parts.append(f"รวม {act['answered']} ข้อ")
    return " · ".join(parts)


def _activity_summary(learner) -> list[dict]:
    """แต่ละคนใช้ส่วนไหนของระบบไปแล้วบ้าง — ตลอดเวลาที่ผ่านมา ไม่ใช่แค่ 30 วัน"""
    drills = DrillSession.objects.filter(learner=learner, finished_at__isnull=False)
    reviews = ReviewSession.objects.filter(learner=learner, answered__gte=1)
    mocks = MockExam.objects.filter(learner=learner, finished_at__isnull=False)
    placements = PlacementTest.objects.filter(learner=learner, finished_at__isnull=False)
    word_orders = WordOrderAttempt.objects.filter(learner=learner)

    return [
        {"key": "drill", "label": ACTIVITY_LABEL["drill"], "count": drills.count(),
         "unit": "ชุด", "answered": sum(s.answered for s in drills)},
        {"key": "review", "label": ACTIVITY_LABEL["review"], "count": reviews.count(),
         "unit": "รอบ", "answered": sum(s.answered for s in reviews)},
        {"key": "mock", "label": ACTIVITY_LABEL["mock"], "count": mocks.count(),
         "unit": "ครั้ง", "answered": 0},
        {"key": "word_order", "label": ACTIVITY_LABEL["word_order"], "count": word_orders.count(),
         "unit": "ข้อ", "answered": 0},
        {"key": "placement", "label": ACTIVITY_LABEL["placement"], "count": placements.count(),
         "unit": "ครั้ง", "answered": 0},
    ]


def group_progress(today=None) -> list[dict]:
    """สรุปของผู้เรียนทุกคนในระบบ เรียงตามคนที่ยังไม่ทำวันนี้ขึ้นก่อน

    เรียงแบบนี้เพราะหน้านี้มีไว้ให้เห็นว่า "ใครยังไม่ทำ" ไม่ใช่ "ใครเก่งกว่า"
    ไม่มีอันดับ 1-2-3 โดยตั้งใจ
    """
    today = today or timezone.localdate()
    window = [today - timedelta(days=i) for i in range(CALENDAR_DAYS - 1, -1, -1)]

    rows = []
    for learner in LearnerProfile.objects.select_related("user").order_by("user__first_name", "user__username"):
        dates = _drill_dates(learner)
        sessions = DrillSession.objects.filter(learner=learner)
        today_session = sessions.filter(started_at__date=today).first()
        acts = _activity_by_date(learner, window)
        logins = set(
            LoginDay.objects
            .filter(user=learner.user, date__gte=window[0])
            .values_list("date", flat=True)
        )

        calendar = []
        for d in window:
            act = acts[d]
            act["login"] = d in logins
            # สามระดับ: ทำชุดหลัก · ทำอย่างอื่น · ไม่ได้ทำ
            # แยกระดับกลางออกมาเพราะวันที่ทวนคำศัพท์อย่างเดียวไม่ใช่วันที่หายไป
            if act["drill"]:
                level = "full"
            elif act["review"] or act["mock"] or act["word_order"]:
                level = "some"
            elif act["login"]:
                # เข้ามาแล้วแต่ไม่ได้ทำอะไร ต่างจากไม่ได้เข้าเลย
                # ระดับนี้บอกว่า "ตั้งใจจะทำแต่ไม่ได้ทำ" ซึ่งเป็นสัญญาณคนละแบบ
                level = "seen"
            else:
                level = "none"
            calendar.append({
                "date": d, "level": level, "done": bool(act["drill"]),
                "label": f"{d.strftime('%-d/%-m')} · {_day_label(d, act)}",
            })

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
            "calendar": calendar,
            "active_days": sum(1 for c in calendar if c["level"] != "none"),
            "drill_days": sum(1 for c in calendar if c["level"] == "full"),
            "activities": _activity_summary(learner),
            "last_login": learner.user.last_login,
            "login_days": sum(1 for d in window if d in logins),
            "logged_in_today": today in logins,
        })

    rows.sort(key=lambda r: (r["done_today"], -r["streak"]))
    return rows
