"""ค่าคงที่และ abstract model ที่ใช้ร่วมกันทุกโมดูล"""
from django.db import models


class Standard(models.TextChoices):
    """มาตรฐานข้อสอบ HSK — เก็บเป็น data ไม่ hard-code (ดู CLAUDE.md D1)"""
    V2 = "2.0", "HSK 2.0 (ใช้อยู่ปัจจุบัน)"
    V3 = "3.0", "HSK 3.0 (มาตรฐานใหม่)"


class SourceType(models.TextChoices):
    """ที่มาของเนื้อหา — ตัวชี้ขาดว่าเอาไปขายได้หรือไม่ (ดู CLAUDE.md D6)"""
    OFFICIAL_PAST_PAPER = "official_past_paper", "ข้อสอบเก่าทางการ (ลิขสิทธิ์ ห้ามขาย)"
    TEXTBOOK = "textbook", "หนังสือเตรียมสอบ (ลิขสิทธิ์ ห้ามขาย)"
    AI_GENERATED = "ai_generated", "สร้างด้วย AI"
    HAND_WRITTEN = "hand_written", "เขียนเอง"
    PUBLIC_DOMAIN = "public_domain", "สาธารณสมบัติ"


class Section(models.TextChoices):
    """พาร์ทของข้อสอบ"""
    LISTENING = "listening", "听力 ฟัง"
    READING = "reading", "阅读 อ่าน"
    WRITING = "writing", "书写 เขียน"
    VOCAB = "vocab", "คำศัพท์ (ฝึกเอง ไม่ใช่พาร์ทในข้อสอบ)"


class ErrorCode(models.TextChoices):
    """สาเหตุที่ตอบผิด — หัวใจของระบบ (ดู CLAUDE.md D8)

    'ผิด 12 ข้อ' ไม่บอกอะไร
    'ผิดเพราะไม่ทันเวลา 8 ใน 12' บอกว่าต้องฝึกความเร็ว ไม่ใช่ท่องศัพท์เพิ่ม
    """
    VOCAB = "VOCAB", "ไม่รู้คำศัพท์คำนั้นเลย"
    MEANING = "MEANING", "รู้คำ แต่เลือกความหมายผิดในบริบท"
    STRUCTURE = "STRUCTURE", "รู้คำครบ แต่จับโครงสร้างประโยคผิด"
    TOO_SLOW = "TOO_SLOW", "รู้คำตอบ แต่ไม่ทันเวลา"
    SOUND = "SOUND", "ฟังไม่ออกทั้งที่รู้คำนั้น"
    CARELESS = "CARELESS", "เผลอ อ่านโจทย์ไม่ครบ"

    @classmethod
    def advice(cls, code):
        return {
            cls.VOCAB: "คำนั้นเข้าคิวทบทวนถี่ขึ้น ถ้าเกิน 40% ของข้อผิด แปลว่าคลังคำยังไม่พอ",
            cls.MEANING: "ปัญหา 近义词 — ไปฝึกชุดแยกคำใกล้เคียง ไม่ใช่ท่องคำเพิ่ม",
            cls.STRUCTURE: "ทบทวนจุดไวยากรณ์ ไม่ใช่คำศัพท์ — เพิ่มเวลาเรียงประโยค",
            cls.TOO_SLOW: "ปัญหาความเร็ว ไม่ใช่ความรู้ — ฝึกอ่านจับเวลา",
            cls.SOUND: "ต้องทำการ์ดเสียง→ความหมาย และ 听写 ไม่ใช่การ์ดอ่าน",
            cls.CARELESS: "ไม่ต้องเรียนเพิ่ม — ในห้องสอบให้อ่านตัวเลือกครบ 4 ก่อนเลือก",
        }.get(code, "")


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Provenance(models.Model):
    """ทุกตารางที่เก็บ *เนื้อหา* ต้องสืบย้อนที่มาได้

    เจ้าของมีข้อสอบเก่าลิขสิทธิ์อยู่ในเครื่อง — ถ้าไม่มีสามฟิลด์นี้ตั้งแต่ migration แรก
    วันที่จะทำเป็นสินค้าจะแยกไม่ออกว่าอะไรเอาไปขายได้ และ audit ย้อนหลังไม่ได้
    """
    standard = models.CharField(
        max_length=8, choices=Standard.choices, default=Standard.V2, db_index=True,
        verbose_name="มาตรฐาน",
    )
    source_type = models.CharField(
        max_length=32, choices=SourceType.choices, default=SourceType.HAND_WRITTEN,
        db_index=True, verbose_name="ที่มา",
    )
    source_ref = models.CharField(
        max_length=200, blank=True, verbose_name="อ้างอิงที่มา",
        help_text="เช่น H51001 หน้า 3 ข้อ 46",
    )
    commercial_safe = models.BooleanField(
        default=True, db_index=True, verbose_name="ใช้เชิงพาณิชย์ได้",
        help_text="ปิดเสมอสำหรับข้อสอบเก่าและเนื้อหาจากหนังสือ",
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # กันพลาด: ที่มาที่มีลิขสิทธิ์บังคับให้ commercial_safe = False เสมอ
        if self.source_type in (SourceType.OFFICIAL_PAST_PAPER, SourceType.TEXTBOOK):
            self.commercial_safe = False
        super().save(*args, **kwargs)
