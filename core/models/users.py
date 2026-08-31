"""ผู้ใช้และโปรไฟล์ผู้เรียน

multi-user ตั้งแต่ migration แรก (CLAUDE.md D2) — คนเรียนกับคนสร้างเป็นคนละคน
และตั้งใจทำเป็นสินค้า การเติม auth ทีหลังแพงกว่าทำตอนนี้ ~15 เท่า
"""
from django.contrib.auth.models import AbstractUser
from django.db import models

from .base import TimeStamped


class Role(models.TextChoices):
    LEARNER = "learner", "ผู้เรียน"
    COACH = "coach", "โค้ช / ผู้ปกครอง / ครู"
    ADMIN = "admin", "ผู้ดูแลระบบ"


class User(AbstractUser):
    role = models.CharField(
        max_length=16, choices=Role.choices, default=Role.LEARNER,
        db_index=True, verbose_name="บทบาท",
    )
    display_name = models.CharField(max_length=80, blank=True, verbose_name="ชื่อที่แสดง")
    timezone = models.CharField(max_length=64, default="Asia/Bangkok", verbose_name="เขตเวลา")

    class Meta:
        verbose_name = "ผู้ใช้"
        verbose_name_plural = "ผู้ใช้"

    def __str__(self):
        return self.display_name or self.get_username()

    @property
    def is_learner(self):
        return self.role == Role.LEARNER

    @property
    def is_coach(self):
        return self.role in (Role.COACH, Role.ADMIN)


class LearnerProfile(TimeStamped):
    """ค่าตั้งต้นและเป้าหมายของผู้เรียนหนึ่งคน

    ค่า baseline_* คือคะแนนจากข้อสอบเก่าชุดแรกที่ทำจับเวลาจริง
    ตราบใดที่ยังว่าง ตัวเลขพยากรณ์ทุกอย่างในระบบคือการเดา — UI ต้องบอกให้ชัด
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="learner_profile",
        verbose_name="ผู้ใช้",
    )
    coaches = models.ManyToManyField(
        User, blank=True, related_name="coached_learners",
        limit_choices_to={"role__in": [Role.COACH, Role.ADMIN]},
        verbose_name="โค้ชที่ดูข้อมูลได้",
    )

    target_level = models.PositiveSmallIntegerField(default=5, verbose_name="ระดับเป้าหมาย")
    target_exam_date = models.DateField(verbose_name="วันสอบเป้าหมาย")
    backup_exam_date = models.DateField(null=True, blank=True, verbose_name="วันสอบสำรอง")

    daily_minutes_budget = models.PositiveSmallIntegerField(
        default=210, verbose_name="งบเวลาต่อวัน (นาที)",
    )
    new_words_per_day = models.PositiveSmallIntegerField(
        default=14, verbose_name="คำใหม่ต่อวัน",
        help_text="ตัวคุมโหลดจะลดค่านี้เองเมื่อของค้างเกินเพดาน",
    )
    drill_size = models.PositiveSmallIntegerField(
        default=40, verbose_name="ขนาดชุดข้อสอบรายวัน",
        help_text="คงที่โดยตั้งใจ — ส่วนผสมเปลี่ยน ไม่ใช่จำนวน (CLAUDE.md D7)",
    )

    baseline_listening = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="คะแนนฐาน ฟัง")
    baseline_reading = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="คะแนนฐาน อ่าน")
    baseline_writing = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="คะแนนฐาน เขียน")
    baseline_taken_on = models.DateField(null=True, blank=True, verbose_name="วันที่วัดคะแนนฐาน")

    known_vocab_estimate = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="ประมาณจำนวนคำที่รู้",
        help_text="จากการวัดจริงหรือจากครูผู้สอน ไม่ใช่การเดา",
    )
    notes = models.TextField(blank=True, verbose_name="บันทึก")

    # ยินยอมให้คัดลอกงานเขียนออกไปให้ Claude ตรวจ
    # เก็บในฐาน ไม่ใช่ใน session เพราะระบบดีดออกทุกเที่ยงคืน (core/daily_session.py)
    # ถ้าเก็บใน session ผู้เรียนจะต้องกดยินยอมใหม่ทุกวัน จนกลายเป็นการกดผ่านโดยไม่อ่าน
    # และเก็บเป็นเวลาไม่ใช่ True/False เพราะต้องตอบได้ว่ายินยอมเมื่อไหร่
    essay_consent_at = models.DateTimeField(
        null=True, blank=True, verbose_name="ยินยอมให้ส่งงานเขียนไปตรวจเมื่อ",
    )

    class Meta:
        verbose_name = "โปรไฟล์ผู้เรียน"
        verbose_name_plural = "โปรไฟล์ผู้เรียน"

    def __str__(self):
        return f"{self.user} → HSK{self.target_level} {self.target_exam_date}"

    @property
    def baseline_total(self):
        parts = [self.baseline_listening, self.baseline_reading, self.baseline_writing]
        return sum(p for p in parts if p is not None) if any(p is not None for p in parts) else None

    @property
    def has_baseline(self):
        """ยังไม่มี baseline = ตัวเลขพยากรณ์ทั้งหมดเป็นการเดา"""
        return self.baseline_taken_on is not None and self.baseline_total is not None

    def days_to_exam(self, today=None):
        from datetime import date
        return (self.target_exam_date - (today or date.today())).days


class LoginDay(models.Model):
    """วันที่ผู้ใช้เข้าระบบ — หนึ่งแถวต่อคนต่อวัน

    User.last_login เก็บได้แค่ครั้งล่าสุด ตอบไม่ได้ว่า "เข้ามากี่วันใน 30 วัน"
    ซึ่งเป็นตัวเลขที่บอกความสม่ำเสมอได้ตรงกว่าจำนวนชุดที่ทำจบ
    เพราะบางวันเปิดมาแล้วทำไม่จบก็ยังนับว่าไม่ได้หายไป
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="login_days", verbose_name="ผู้ใช้",
    )
    date = models.DateField(db_index=True, verbose_name="วันที่")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="เข้าครั้งแรกของวันเมื่อ")

    class Meta:
        verbose_name = "วันที่เข้าระบบ"
        verbose_name_plural = "วันที่เข้าระบบ"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="uniq_login_per_day"),
        ]

    def __str__(self):
        return f"{self.user} · {self.date}"
