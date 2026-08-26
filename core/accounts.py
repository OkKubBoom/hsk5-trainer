"""สร้างบัญชีผู้เรียน — ใช้ร่วมกันระหว่างคำสั่ง make_learner กับหน้าจัดการผู้ใช้

อยู่ที่เดียวเพื่อไม่ให้สองทางสร้างบัญชีคนละแบบ แล้วเจอผู้เรียนที่ไม่มีการ์ดทีหลัง
"""
from __future__ import annotations

from datetime import date

from django.db import transaction

from .models import Card, CardType, LearnerProfile, Role, User, VocabItem


@transaction.atomic
def create_learner(*, username: str, password: str, display_name: str = "",
                   exam_date: date, backup_exam_date: date | None = None,
                   coach: User | None = None) -> tuple[LearnerProfile, int]:
    """สร้างผู้เรียนหนึ่งคนพร้อมการ์ดทบทวนครบทุกคำในคลัง

    คืนค่า (โปรไฟล์, จำนวนการ์ดที่สร้าง)
    """
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"first_name": display_name, "role": Role.LEARNER},
    )
    if not created:
        raise ValueError(f"มีชื่อผู้ใช้ {username} อยู่แล้ว")

    user.first_name = display_name
    user.set_password(password)
    user.save()

    profile = LearnerProfile.objects.create(
        user=user, target_exam_date=exam_date, backup_exam_date=backup_exam_date,
    )
    if coach:
        profile.coaches.add(coach)

    cards = [
        Card(learner=profile, vocab=v, card_type=CardType.RECOGNIZE)
        for v in VocabItem.objects.exclude(meaning_th="").only("id")
    ]
    Card.objects.bulk_create(cards, batch_size=500)
    return profile, len(cards)
