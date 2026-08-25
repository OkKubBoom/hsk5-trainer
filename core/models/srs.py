"""ตารางทบทวน — ความคืบหน้าของผู้เรียนแต่ละคนต่อคำแต่ละคำ

หนึ่งคำศัพท์สร้างได้หลายการ์ด เพราะ 'จำได้ตอนอ่าน' กับ 'ฟังออก' เป็นคนละทักษะ
พาร์ทฟังเปิดเสียงรอบเดียว ต้องแปลงเสียงเป็นความหมายได้ในไม่ถึงวินาที
การ์ดอ่านอย่างเดียวจึงไม่พอ — นี่คือจุดที่ผู้เรียนไทยตกบ่อยที่สุด
"""
from django.db import models

from .base import TimeStamped
from .users import LearnerProfile
from .lexicon import VocabItem


class CardType(models.TextChoices):
    RECOGNIZE = "recognize", "อ่าน 汉字 → ความหมาย"
    AUDIO = "audio", "ฟังเสียง → ความหมาย"
    CLOZE = "cloze", "เติมคำในช่องว่าง / แยกคำใกล้เคียง"
    PRODUCE = "produce", "ความหมาย → พิมพ์ 汉字"


class CardState(models.TextChoices):
    NEW = "new", "ยังไม่เคยเรียน"
    LEARNING = "learning", "กำลังเรียน"
    REVIEW = "review", "อยู่ในรอบทบทวน"
    LAPSED = "lapsed", "เคยจำได้แล้วลืม"
    SUSPENDED = "suspended", "พักไว้"


class Card(TimeStamped):
    learner = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="cards", verbose_name="ผู้เรียน",
    )
    vocab = models.ForeignKey(
        VocabItem, on_delete=models.CASCADE, related_name="cards", verbose_name="คำศัพท์",
    )
    card_type = models.CharField(
        max_length=16, choices=CardType.choices, default=CardType.RECOGNIZE, verbose_name="ชนิดการ์ด",
    )
    state = models.CharField(
        max_length=16, choices=CardState.choices, default=CardState.NEW,
        db_index=True, verbose_name="สถานะ",
    )

    due_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="ถึงกำหนดทบทวน",
    )
    interval_days = models.FloatField(default=0, verbose_name="ระยะห่างปัจจุบัน (วัน)")
    ease = models.FloatField(default=2.5, verbose_name="ค่าความง่าย")
    reps = models.PositiveIntegerField(default=0, verbose_name="ทบทวนไปกี่ครั้ง")
    lapses = models.PositiveIntegerField(default=0, verbose_name="ลืมไปกี่ครั้ง")
    last_reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="ทบทวนล่าสุด")

    class Meta:
        verbose_name = "การ์ดทบทวน"
        verbose_name_plural = "การ์ดทบทวน"
        constraints = [
            models.UniqueConstraint(
                fields=["learner", "vocab", "card_type"], name="uniq_card_learner_vocab_type",
            ),
        ]
        indexes = [
            models.Index(fields=["learner", "state", "due_at"]),
            models.Index(fields=["learner", "due_at"]),
        ]

    def __str__(self):
        return f"{self.vocab.hanzi} [{self.get_card_type_display()}]"

    @property
    def is_new(self):
        return self.state == CardState.NEW


class Rating(models.IntegerChoices):
    """ผลการทบทวนหนึ่งครั้ง"""
    AGAIN = 1, "ลืม"
    HARD = 2, "ยาก"
    GOOD = 3, "จำได้"
    EASY = 4, "ง่าย"


class ReviewLog(models.Model):
    """บันทึกทุกครั้งที่ทบทวน — ห้ามลบ

    เก็บ scheduler_version ไว้เพราะวันหนึ่งจะเปลี่ยนอัลกอริทึม
    แล้วต้องรู้ว่าข้อมูลชุดไหนมาจากตัวจัดตารางแบบไหน
    """
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="reviews", verbose_name="การ์ด")
    reviewed_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="เวลา")
    rating = models.PositiveSmallIntegerField(choices=Rating.choices, verbose_name="ผล")
    elapsed_ms = models.PositiveIntegerField(default=0, verbose_name="ใช้เวลา (มิลลิวินาที)")
    prev_interval_days = models.FloatField(default=0, verbose_name="ระยะห่างก่อนหน้า")
    new_interval_days = models.FloatField(default=0, verbose_name="ระยะห่างใหม่")
    scheduler_version = models.CharField(max_length=16, default="sm2d-1", verbose_name="เวอร์ชันตัวจัดตาราง")

    class Meta:
        verbose_name = "ประวัติการทบทวน"
        verbose_name_plural = "ประวัติการทบทวน"
        ordering = ["-reviewed_at"]
        indexes = [models.Index(fields=["card", "-reviewed_at"])]

    def __str__(self):
        return f"{self.card} · {self.get_rating_display()}"
