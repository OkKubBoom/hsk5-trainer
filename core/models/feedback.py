"""บันทึกการตรวจสอบคำอธิบายโดยคน — ของจริงที่มาแทนคำอธิบายของ AI

กติกาข้อ D8 ของโปรเจกต์: ห้ามเชื่อเฉลยที่ AI สร้างโดยไม่มีทางให้ผู้ใช้กดว่าผิด
ตารางนี้คือ "ทาง" นั้น และเก็บสิ่งที่ผู้ใช้ค้นมาได้ไว้ใช้ต่อ ไม่ใช่แค่รับแจ้งแล้วทิ้ง
"""
from django.db import models

from .base import TimeStamped
from .content import Question
from .lexicon import VocabItem
from .users import User


class NoteVerdict(models.TextChoices):
    WRONG = "wrong", "คำอธิบายนี้ผิด"
    CORRECTED = "corrected", "ผิด และนี่คือคำอธิบายที่ถูก"
    CONFIRMED = "confirmed", "ตรวจแล้ว ถูกต้อง"


class NoteStatus(models.TextChoices):
    OPEN = "open", "รอเจ้าของระบบดู"
    ACCEPTED = "accepted", "รับมาใช้แทนคำอธิบายเดิม"
    REJECTED = "rejected", "ไม่รับ"


class ExplanationNote(TimeStamped):
    # แย้งได้ทั้งคำอธิบายเฉลยและคำแปลศัพท์ — ใช้ตารางเดียวกันเพื่อให้หน้าตรวจมีที่เดียว
    question = models.ForeignKey(
        Question, null=True, blank=True, on_delete=models.CASCADE,
        related_name="notes", verbose_name="คำถาม",
    )
    vocab = models.ForeignKey(
        VocabItem, null=True, blank=True, on_delete=models.CASCADE,
        related_name="notes", verbose_name="คำศัพท์",
    )
    author = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="explanation_notes",
        verbose_name="ผู้ส่ง",
    )
    verdict = models.CharField(
        max_length=16, choices=NoteVerdict.choices, db_index=True, verbose_name="ผลการตรวจ",
    )
    submission = models.ForeignKey(
        "core.WritingSubmission", null=True, blank=True, on_delete=models.CASCADE,
        related_name="notes", verbose_name="งานเขียนที่แย้ง",
    )
    # แย้งคอลัมน์ไหนของคำศัพท์ — คำเดียวมีหลายอย่างให้แย้งได้
    # ว่างไว้ = แย้งคำอธิบายเฉลยของข้อสอบ (พฤติกรรมเดิม)
    field_name = models.CharField(
        max_length=32, blank=True, default="", verbose_name="แย้งเรื่องอะไร",
        help_text="pinyin · pinyin_sandhi · meaning_th",
    )
    body = models.TextField(
        blank=True, verbose_name="คำอธิบายที่ถูกต้อง",
        help_text="สิ่งที่ผู้ใช้ค้นมาได้ — จะถูกแสดงแทนของ AI เมื่อเจ้าของระบบรับแล้ว",
    )
    source = models.CharField(
        max_length=300, blank=True, verbose_name="อ้างอิงจากไหน",
        help_text="เช่น ครูที่สอน · หนังสือเตรียมสอบหน้า 42 · ลิงก์",
    )
    status = models.CharField(
        max_length=16, choices=NoteStatus.choices, default=NoteStatus.OPEN,
        db_index=True, verbose_name="สถานะ",
    )

    class Meta:
        verbose_name = "การตรวจคำอธิบาย"
        verbose_name_plural = "การตรวจคำอธิบาย"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["question", "-created_at"]),
            models.Index(fields=["vocab", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                # ต้องผูกกับอย่างใดอย่างหนึ่งเสมอ ไม่ใช่ทั้งคู่ และไม่ใช่ไม่มีเลย
                condition=(
                    models.Q(question__isnull=False, vocab__isnull=True, submission__isnull=True)
                    | models.Q(question__isnull=True, vocab__isnull=False, submission__isnull=True)
                    | models.Q(question__isnull=True, vocab__isnull=True, submission__isnull=False)
                ),
                name="note_targets_exactly_one",
            ),
        ]

    def __str__(self):
        return f"{self.target_label} · {self.get_verdict_display()}"

    @property
    def target_label(self):
        """ชื่อสิ่งที่ถูกแย้ง — ใช้แสดงในหน้าตรวจโดยไม่ต้องรู้ว่าเป็นข้อสอบหรือคำศัพท์"""
        if self.vocab_id:
            return f"คำศัพท์ {self.vocab.hanzi}"
        if self.question_id:
            return self.question.source_ref or f"ข้อ {self.question_id}"
        return "—"

    @property
    def is_usable(self):
        """คำอธิบายจากคนที่พร้อมเอาไปแสดงแทนของ AI"""
        return self.status == NoteStatus.ACCEPTED and bool(self.body)
