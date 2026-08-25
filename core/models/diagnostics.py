"""ErrorLog — ตารางกลางที่ทั้งสามทักษะเขียนลงร่วมกัน

นี่คือเหตุผลเดียวที่ระบบนี้ควรมีอยู่ Anki ท่องศัพท์เก่งกว่า Du Chinese มีบทอ่านดีกว่า
แต่ไม่มีใครตอบได้ว่า "ผิดเพราะอะไร" ข้ามทักษะ แล้วเอาคำตอบนั้นมาปรับชุดข้อสอบพรุ่งนี้

ตารางนี้ป้อนสองอย่าง:
  1. 30% ของชุดข้อสอบประจำวัน (ดู core/selection.py)
  2. คำแนะนำว่าควรไปฝึกอะไรต่อ (ดู ErrorCode.advice)
"""
from django.db import models
from django.utils import timezone

from .base import ErrorCode, Section, TimeStamped
from .content import Question
from .lexicon import GrammarPoint, VocabItem
from .users import LearnerProfile


class ErrorLog(TimeStamped):
    learner = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="errors", verbose_name="ผู้เรียน",
    )
    code = models.CharField(
        max_length=16, choices=ErrorCode.choices, db_index=True, verbose_name="สาเหตุ",
    )
    section = models.CharField(
        max_length=16, choices=Section.choices, db_index=True, verbose_name="พาร์ท",
    )

    label = models.CharField(
        max_length=200, verbose_name="สิ่งที่ผิด",
        help_text="คำ ประโยค หรือหัวข้อไวยากรณ์ — เก็บเป็นข้อความเพื่อให้ยังอ่านออกแม้ลบ FK ทิ้ง",
    )
    vocab = models.ForeignKey(
        VocabItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="errors", verbose_name="คำศัพท์",
    )
    grammar = models.ForeignKey(
        GrammarPoint, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="errors", verbose_name="จุดไวยากรณ์",
    )
    question = models.ForeignKey(
        Question, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="errors", verbose_name="คำถามล่าสุดที่ผิด",
    )

    miss_count = models.PositiveIntegerField(default=1, db_index=True, verbose_name="ผิดไปกี่ครั้ง")
    first_seen_at = models.DateTimeField(auto_now_add=True, verbose_name="ผิดครั้งแรก")
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True, verbose_name="ผิดล่าสุด")
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="แก้ได้แล้วเมื่อ")

    class Meta:
        verbose_name = "บันทึกข้อผิด"
        verbose_name_plural = "บันทึกข้อผิด"
        ordering = ["-miss_count", "-last_seen_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["learner", "code", "label"], name="uniq_error_learner_code_label",
            ),
        ]
        indexes = [
            models.Index(fields=["learner", "resolved_at", "-miss_count"]),
            models.Index(fields=["learner", "-last_seen_at"]),
        ]

    def __str__(self):
        return f"{self.label} · {self.get_code_display()} ×{self.miss_count}"

    @property
    def is_open(self):
        return self.resolved_at is None

    @property
    def advice_th(self):
        return ErrorCode.advice(self.code)

    def priority_score(self, now=None):
        """คะแนนความเร่งด่วน — ใช้เรียงว่าข้อไหนควรกลับมาถามก่อน

        ผิดบ่อย × ผิดเมื่อเร็วๆ นี้ ควรมาก่อนข้อที่ผิดครั้งเดียวเมื่อเดือนที่แล้ว
        """
        now = now or timezone.now()
        days_ago = max(0.0, (now - self.last_seen_at).total_seconds() / 86400.0)
        recency = 1.0 / (1.0 + days_ago / 7.0)  # ครึ่งชีวิตประมาณหนึ่งสัปดาห์
        return self.miss_count * recency

    @classmethod
    def record(cls, learner, code, label, *, section, vocab=None, grammar=None, question=None):
        """บันทึกข้อผิดหนึ่งครั้ง — ถ้าเคยผิดแบบเดียวกันแล้วให้เพิ่มตัวนับ"""
        obj, created = cls.objects.get_or_create(
            learner=learner, code=code, label=label,
            defaults={"section": section, "vocab": vocab, "grammar": grammar, "question": question},
        )
        if not created:
            obj.miss_count += 1
            obj.last_seen_at = timezone.now()
            obj.resolved_at = None
            obj.question = question or obj.question
            obj.save(update_fields=["miss_count", "last_seen_at", "resolved_at", "question", "updated_at"])
        return obj

    def resolve(self):
        self.resolved_at = timezone.now()
        self.save(update_fields=["resolved_at", "updated_at"])
