"""คลังคำศัพท์ ไวยากรณ์ และสเปกข้อสอบ"""
from django.db import models

from .base import Provenance, Section, Standard, TimeStamped


class ExamSpec(TimeStamped):
    """โครงสร้างข้อสอบหนึ่งมาตรฐาน — เก็บเป็น data เพื่อรองรับ 2.0 → 3.0

    ถ้า hard-code ว่า '阅读 45 ข้อ' ไว้ในโค้ด วันที่ HSK 3.0 มาจริง (35 ข้อ)
    จะต้องไล่แก้ทั้งระบบ ตารางนี้ทำให้เปลี่ยนแถวเดียวจบ
    """
    standard = models.CharField(max_length=8, choices=Standard.choices, verbose_name="มาตรฐาน")
    level = models.PositiveSmallIntegerField(default=5, verbose_name="ระดับ")
    vocab_size = models.PositiveIntegerField(verbose_name="จำนวนคำศัพท์สะสม")
    total_score = models.PositiveSmallIntegerField(default=300, verbose_name="คะแนนเต็ม")
    pass_score = models.PositiveSmallIntegerField(default=180, verbose_name="คะแนนผ่าน")
    per_section_minimum = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="ขั้นต่ำรายพาร์ท",
        help_text="ว่าง = ไม่มีขั้นต่ำ ตัดสินที่คะแนนรวมอย่างเดียว (HSK5 2.0 เป็นแบบนี้)",
    )
    sections = models.JSONField(
        default=dict, verbose_name="โครงสร้างพาร์ท",
        help_text='เช่น {"listening": {"questions": 45, "minutes": 30, "numbers": [1, 45]}}',
    )
    is_active = models.BooleanField(default=False, db_index=True, verbose_name="ใช้อยู่ปัจจุบัน")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")

    class Meta:
        verbose_name = "สเปกข้อสอบ"
        verbose_name_plural = "สเปกข้อสอบ"
        constraints = [
            models.UniqueConstraint(fields=["standard", "level"], name="uniq_spec_standard_level"),
        ]

    def __str__(self):
        return f"HSK{self.level} · {self.standard}"


class VocabItem(Provenance, TimeStamped):
    """คำศัพท์หนึ่งคำ — ใช้ร่วมกันทุกผู้เรียน (ความคืบหน้าอยู่ที่ Card)"""
    hanzi = models.CharField(max_length=32, db_index=True, verbose_name="汉字")
    pinyin = models.CharField(max_length=96, verbose_name="pinyin")
    meaning_th = models.CharField(max_length=255, verbose_name="ความหมาย (ไทย)")
    meaning_en = models.CharField(max_length=255, blank=True, verbose_name="ความหมาย (อังกฤษ)")
    pos = models.CharField(max_length=24, blank=True, verbose_name="ชนิดคำ")

    hsk_level = models.PositiveSmallIntegerField(default=5, db_index=True, verbose_name="ระดับ HSK")
    frequency_rank = models.PositiveIntegerField(
        null=True, blank=True, db_index=True, verbose_name="อันดับความถี่",
        help_text="เลขน้อย = เจอบ่อยกว่า ใช้จัดลำดับว่าควรเรียนคำไหนก่อน",
    )
    tags = models.JSONField(
        default=list, blank=True, verbose_name="แท็ก",
        help_text='เช่น ["conn", "idiom"] — conn = คำเชื่อมที่ใช้ในเรียงความ',
    )

    example_zh = models.CharField(max_length=255, blank=True, verbose_name="ประโยคตัวอย่าง")
    example_th = models.CharField(max_length=255, blank=True, verbose_name="แปลประโยค")
    audio = models.ForeignKey(
        "core.AudioClip", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="vocab_items", verbose_name="ไฟล์เสียง",
    )

    class Meta:
        verbose_name = "คำศัพท์"
        verbose_name_plural = "คำศัพท์"
        ordering = ["frequency_rank", "hanzi"]
        constraints = [
            models.UniqueConstraint(fields=["hanzi", "standard"], name="uniq_vocab_hanzi_standard"),
        ]
        indexes = [models.Index(fields=["hsk_level", "frequency_rank"])]

    def __str__(self):
        return f"{self.hanzi} ({self.pinyin})"


class SynonymGroup(TimeStamped):
    """กลุ่มคำใกล้เคียง — 阅读第一部分 คือข้อสอบแยกคำใกล้เคียงล้วน

    15 ข้อจาก 45 ของพาร์ทอ่าน = 33% ของคะแนนอ่าน มาจากตรงนี้ทั้งหมด
    ตัวอย่าง: 承认 / 承担 / 承受 · 改善 / 改进 / 改正
    """
    name = models.CharField(max_length=120, verbose_name="ชื่อกลุ่ม")
    items = models.ManyToManyField(VocabItem, related_name="synonym_groups", verbose_name="คำในกลุ่ม")
    note_th = models.TextField(verbose_name="วิธีแยกความต่าง (ไทย)")

    class Meta:
        verbose_name = "กลุ่มคำใกล้เคียง"
        verbose_name_plural = "กลุ่มคำใกล้เคียง"

    def __str__(self):
        return self.name


class GrammarPoint(Provenance, TimeStamped):
    """จุดไวยากรณ์ที่แยก HSK4 ออกจาก HSK5"""
    title_zh = models.CharField(max_length=120, verbose_name="หัวข้อ (จีน)")
    title_th = models.CharField(max_length=160, verbose_name="หัวข้อ (ไทย)")
    hsk_level = models.PositiveSmallIntegerField(default=5, verbose_name="ระดับ HSK")
    section = models.CharField(
        max_length=16, choices=Section.choices, default=Section.WRITING, verbose_name="พาร์ทที่ใช้",
    )
    explanation_th = models.TextField(verbose_name="คำอธิบาย (ไทย)")
    patterns = models.JSONField(
        default=list, blank=True, verbose_name="รูปประโยค",
        help_text='เช่น ["随着 + N的 + 变化，+ ประโยคหลัก"]',
    )
    priority = models.PositiveSmallIntegerField(
        default=50, verbose_name="ลำดับความสำคัญ", help_text="น้อย = สำคัญกว่า",
    )

    class Meta:
        verbose_name = "จุดไวยากรณ์"
        verbose_name_plural = "จุดไวยากรณ์"
        ordering = ["priority", "title_zh"]

    def __str__(self):
        return f"{self.title_zh} — {self.title_th}"


class WritingTemplate(Provenance, TimeStamped):
    """เทมเพลตเรียงความสำเร็จรูป — พาร์ทที่ถูกที่สุด 7-11 ชม. ต่อ 10 คะแนน"""
    name = models.CharField(max_length=160, verbose_name="ชื่อเทมเพลต")
    body_zh = models.TextField(verbose_name="เทมเพลต (จีน)")
    body_th = models.TextField(verbose_name="คำอธิบาย (ไทย)")
    approx_chars = models.PositiveSmallIntegerField(default=90, verbose_name="ความยาวโดยประมาณ")
    use_case = models.CharField(max_length=160, blank=True, verbose_name="ใช้กับโจทย์แบบไหน")

    class Meta:
        verbose_name = "เทมเพลตเรียงความ"
        verbose_name_plural = "เทมเพลตเรียงความ"

    def __str__(self):
        return self.name
