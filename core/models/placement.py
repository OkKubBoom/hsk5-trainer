"""แบบวัดระดับ — ทำครั้งเดียวตอนเริ่ม เพื่อเลิกเดาว่าผู้เรียนอยู่ตรงไหน

ตราบใดที่ยังไม่มีผลชุดนี้ ตัวเลขทุกอย่างในระบบ (โควตาคำใหม่ วันที่จะครบ
ความยากของชุด) คือการเดา — UI ต้องบอกให้ชัด ไม่ใช่แสดงเป็นตัวเลขที่ดูน่าเชื่อ
"""
from django.db import models
from django.utils import timezone

from .base import TimeStamped
from .lexicon import VocabItem
from .users import LearnerProfile


class PlacementTest(TimeStamped):
    learner = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="placement_tests",
        verbose_name="ผู้เรียน",
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="เริ่ม")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="เสร็จ")
    planned_size = models.PositiveSmallIntegerField(default=80, verbose_name="จำนวนคำที่วัด")
    result = models.JSONField(
        default=dict, blank=True, verbose_name="ผลที่คำนวณได้",
        help_text='เช่น {"by_level": {"4": {"asked": 20, "known": 14}}, "known_vocab_estimate": 1420}',
    )

    class Meta:
        verbose_name = "แบบวัดระดับ"
        verbose_name_plural = "แบบวัดระดับ"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.learner.user} · วัดระดับ {self.started_at:%Y-%m-%d}"

    @property
    def is_done(self):
        return self.finished_at is not None

    @property
    def answered_count(self):
        return self.answers.count()

    def finish(self):
        self.finished_at = timezone.now()
        self.save(update_fields=["finished_at", "updated_at"])


class PlacementAnswer(models.Model):
    """หนึ่งคำที่ถาม — เก็บ 'กดไม่รู้' แยกจาก 'ตอบผิด' เพราะสองอย่างนี้ไม่เหมือนกัน

    ตอบผิด = รู้จักคำแต่จำความหมายสลับ (แก้ด้วยการฝึกแยกคำใกล้เคียง)
    กดไม่รู้ = ไม่เคยเห็นคำนี้ (แก้ด้วยการเรียนคำใหม่)
    """
    test = models.ForeignKey(
        PlacementTest, on_delete=models.CASCADE, related_name="answers", verbose_name="แบบวัดระดับ",
    )
    vocab = models.ForeignKey(
        VocabItem, on_delete=models.CASCADE, related_name="placement_answers", verbose_name="คำศัพท์",
    )
    hsk_level = models.PositiveSmallIntegerField(db_index=True, verbose_name="ระดับของคำ")
    given = models.CharField(max_length=255, blank=True, verbose_name="คำตอบที่เลือก")
    is_correct = models.BooleanField(default=False, verbose_name="ถูก")
    said_unknown = models.BooleanField(default=False, verbose_name="กดว่ายังไม่รู้")
    elapsed_ms = models.PositiveIntegerField(default=0, verbose_name="ใช้เวลา (มิลลิวินาที)")
    answered_at = models.DateTimeField(auto_now_add=True, verbose_name="ตอบเมื่อ")

    class Meta:
        verbose_name = "คำตอบในแบบวัดระดับ"
        verbose_name_plural = "คำตอบในแบบวัดระดับ"
        ordering = ["answered_at"]
        constraints = [
            models.UniqueConstraint(fields=["test", "vocab"], name="uniq_placement_test_vocab"),
        ]

    def __str__(self):
        return f"{self.vocab.hanzi} · {'ถูก' if self.is_correct else 'ผิด'}"
