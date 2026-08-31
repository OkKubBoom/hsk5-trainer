"""ข้อมูลที่ต้องอยู่บนทุกหน้า — ใส่ผ่าน context processor ไม่ต้องส่งผ่านทุก view

นับถอยหลังวันสอบ · จำนวนงานที่รอเจ้าของระบบตรวจ
เหตุผลที่ต้องอยู่ทุกหน้า ไม่ใช่แค่หน้าแรก — จำนวนวันที่เหลือคือสิ่งเดียวที่
เปลี่ยนความหมายของทุกอย่างบนหน้าจอ ชุดฝึก 40 ข้อตอนเหลือ 100 วัน
กับตอนเหลือ 10 วัน ควรทำให้รู้สึกต่างกัน
"""
from __future__ import annotations

from django.utils import timezone


def _round(label: str, exam_date, today) -> dict | None:
    if not exam_date:
        return None
    left = (exam_date - today).days
    return {
        "label": label,
        "date": exam_date,
        "days": left,
        "passed": left < 0,
        # ระดับความเร่ง ใช้เลือกสีบนหน้าจอ
        # 14 วันคือช่วง freeze (หยุดคำใหม่) ตาม settings.SRS_FREEZE_DAYS
        "level": (
            "passed" if left < 0
            else "now" if left <= 14
            else "soon" if left <= 30
            else "far"
        ),
    }


def exam_countdown(request) -> dict:
    """เหลือกี่วันถึงวันสอบ — ทั้งรอบหลักและรอบสำรอง

    บัญชีผู้ดูแลที่ไม่มีโปรไฟล์ผู้เรียนจะไม่มีวันสอบ — คืนค่าว่าง
    ให้เทมเพลตข้ามไปเลย ไม่ใช่โชว์ 0 วันซึ่งอ่านผิดความหมาย
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"exam_rounds": []}

    profile = getattr(user, "learner_profile", None)
    if profile is None:
        return {"exam_rounds": []}

    today = timezone.localdate()
    rounds = [
        _round("รอบแรก", profile.target_exam_date, today),
        _round("รอบสำรอง", profile.backup_exam_date, today),
    ]
    return {"exam_rounds": [r for r in rounds if r]}


def pending_work(request) -> dict:
    """งานที่รอเจ้าของระบบทำ — ขึ้นเป็นตัวเลขข้างเมนู

    ต้องอยู่ทุกหน้า เพราะทางถ่ายทอดผลตรวจเรียงความมีเจ้าของระบบเป็นคอขวด
    ถ้าต้องเปิดหน้าคิวเองถึงจะรู้ว่ามีคนรออยู่ ผู้เรียนจะรอข้ามวัน
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"pending_essays": 0}
    if not (user.is_superuser or getattr(user, "role", "") == "admin"):
        return {"pending_essays": 0}

    from .models import WritingSubmission
    return {
        "pending_essays": WritingSubmission.objects.filter(review_state="requested").count(),
    }
