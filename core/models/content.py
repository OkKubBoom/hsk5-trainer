"""เนื้อหาข้อสอบ — เสียง บทอ่าน คำถาม ตัวเลือก

หลักการที่ห้ามลืม: เฉลยผิดแบบเงียบคือความเสี่ยงที่ร้ายที่สุดของระบบนี้
ถ้าเฉลยผิด คำอธิบายจะอธิบายเหตุผลของเฉลยที่ผิดอย่างมั่นใจ และผู้เรียนระดับ HSK4
ไม่มีทางจับได้ ฝึกไป 500 ข้อ = เรียนภาษาจีนผิด 500 จุด
→ ทุกคำถามต้องกดรายงานว่าเฉลยผิดได้ แล้วพักข้อนั้นทันที (status = SUSPENDED)
"""
from django.db import models

from .base import Provenance, Section, TimeStamped
from .lexicon import GrammarPoint, SynonymGroup, VocabItem


class AudioClip(Provenance, TimeStamped):
    title = models.CharField(max_length=160, verbose_name="ชื่อ")
    file = models.FileField(upload_to="audio/", blank=True, verbose_name="ไฟล์เสียง")
    external_path = models.CharField(
        max_length=400, blank=True, verbose_name="พาธไฟล์ภายนอก",
        help_text="ใช้กับไฟล์ลิขสิทธิ์ที่ไม่ควรอัปโหลดเข้าระบบ ชี้ไปที่ไฟล์ในเครื่องแทน",
    )
    transcript_zh = models.TextField(blank=True, verbose_name="บทถอดเสียง")
    duration_ms = models.PositiveIntegerField(default=0, verbose_name="ความยาว (มิลลิวินาที)")
    voice = models.CharField(max_length=64, blank=True, verbose_name="เสียงที่ใช้")
    speed = models.FloatField(default=1.0, verbose_name="ความเร็ว")

    class Meta:
        verbose_name = "ไฟล์เสียง"
        verbose_name_plural = "ไฟล์เสียง"

    def __str__(self):
        return self.title


class GroupKind(models.TextChoices):
    LISTENING_DIALOG = "listening_dialog", "บทสนทนาสั้น (听力第一部分)"
    LISTENING_PASSAGE = "listening_passage", "บทยาว (听力第二部分)"
    READING_CLOZE = "reading_cloze", "เติมคำในช่องว่าง (阅读第一部分)"
    READING_MATCH = "reading_match", "เลือกประโยคที่ตรง (阅读第二部分)"
    READING_PASSAGE = "reading_passage", "บทอ่านยาว (阅读第三部分)"


class ItemGroup(Provenance, TimeStamped):
    """ชุดเนื้อหาที่มีหลายคำถามอ้างถึง เช่น บทอ่านหนึ่งบทมี 4 คำถาม"""
    kind = models.CharField(max_length=32, choices=GroupKind.choices, db_index=True, verbose_name="ชนิด")
    section = models.CharField(max_length=16, choices=Section.choices, db_index=True, verbose_name="พาร์ท")
    title = models.CharField(max_length=160, blank=True, verbose_name="หัวเรื่อง")
    passage_zh = models.TextField(blank=True, verbose_name="เนื้อหา (จีน)")
    passage_th = models.TextField(blank=True, verbose_name="คำแปล (ไทย)")
    audio = models.ForeignKey(
        AudioClip, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="groups", verbose_name="ไฟล์เสียง",
    )
    char_count = models.PositiveIntegerField(default=0, verbose_name="จำนวนตัวอักษร")
    difficulty = models.PositiveSmallIntegerField(
        default=3, verbose_name="ความยาก", help_text="1 ง่ายสุด – 5 ยากสุด",
    )

    class Meta:
        verbose_name = "ชุดเนื้อหา"
        verbose_name_plural = "ชุดเนื้อหา"

    def __str__(self):
        return self.title or f"{self.get_kind_display()} #{self.pk}"


class QuestionType(models.TextChoices):
    VOCAB_MC = "vocab_mc", "คำศัพท์ปรนัย"
    VOCAB_RECALL = "vocab_recall", "นึกคำจากความหมาย"
    SYNONYM_CLOZE = "synonym_cloze", "เลือกคำใกล้เคียงให้ตรงบริบท"
    WORD_ORDER = "word_order", "เรียงคำเป็นประโยค (完成句子)"
    READING_MC = "reading_mc", "อ่านแล้วตอบปรนัย"
    LISTENING_MC = "listening_mc", "ฟังแล้วตอบปรนัย"
    DICTATION = "dictation", "听写 ฟังแล้วพิมพ์"
    WRITING_PROMPT = "writing_prompt", "โจทย์เขียนเรียงความ"


class QuestionStatus(models.TextChoices):
    DRAFT = "draft", "ร่าง"
    ACTIVE = "active", "ใช้งาน"
    SUSPENDED = "suspended", "พักไว้ (สงสัยเฉลยผิด)"
    RETIRED = "retired", "เลิกใช้"


class Question(Provenance, TimeStamped):
    group = models.ForeignKey(
        ItemGroup, null=True, blank=True, on_delete=models.CASCADE,
        related_name="questions", verbose_name="ชุดเนื้อหา",
    )
    qtype = models.CharField(max_length=24, choices=QuestionType.choices, db_index=True, verbose_name="ชนิดคำถาม")
    section = models.CharField(max_length=16, choices=Section.choices, db_index=True, verbose_name="พาร์ท")
    status = models.CharField(
        max_length=16, choices=QuestionStatus.choices, default=QuestionStatus.ACTIVE,
        db_index=True, verbose_name="สถานะ",
    )

    prompt_zh = models.TextField(verbose_name="โจทย์ (จีน)")
    prompt_th = models.CharField(max_length=255, blank=True, verbose_name="คำสั่ง (ไทย)")
    answer_text = models.CharField(
        max_length=400, blank=True, verbose_name="เฉลย (ข้อเขียน)",
        help_text="ใช้กับข้อที่ไม่ใช่ปรนัย เช่น เรียงคำ หรือ 听写",
    )
    explanation_th = models.TextField(blank=True, verbose_name="คำอธิบายเฉลย (ไทย)")
    # คำอธิบายแบบมีโครงสร้าง 4 ชั้น — เก็บเป็น JSON เพื่อให้หน้าเว็บจัดวางเองได้
    # และตรวจสอบภายหลังได้ว่าชั้นไหนขาด ต่างจากการยัดทุกอย่างลงข้อความก้อนเดียว
    explanation = models.JSONField(
        default=dict, blank=True, verbose_name="คำอธิบาย 4 ชั้น",
        help_text='{"why_correct": "...", "hint": "...", "key_vocab": [...], "rule": "...", "error_code": "..."}',
    )

    difficulty = models.PositiveSmallIntegerField(default=3, db_index=True, verbose_name="ความยาก")
    target_seconds = models.PositiveSmallIntegerField(
        default=60, verbose_name="เวลาเป้าหมาย (วินาที)",
        help_text="阅读第三部分 ควรอยู่ที่ 70 วินาที เกิน 105 ให้เดาแล้วไปต่อ",
    )

    vocab = models.ForeignKey(
        VocabItem, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="questions", verbose_name="คำศัพท์ที่ทดสอบ",
    )
    synonym_group = models.ForeignKey(
        SynonymGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="questions", verbose_name="กลุ่มคำใกล้เคียง",
    )
    grammar = models.ForeignKey(
        GrammarPoint, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="questions", verbose_name="จุดไวยากรณ์",
    )

    flagged_wrong_count = models.PositiveSmallIntegerField(
        default=0, verbose_name="ถูกรายงานว่าเฉลยผิด",
        help_text="ผู้เรียนกดรายงานกี่ครั้ง — เกิน 0 ควรตรวจด้วยตาคน",
    )

    class Meta:
        verbose_name = "คำถาม"
        verbose_name_plural = "คำถาม"
        indexes = [
            models.Index(fields=["section", "qtype", "status"]),
            models.Index(fields=["status", "difficulty"]),
        ]

    def __str__(self):
        return f"[{self.get_qtype_display()}] {self.prompt_zh[:40]}"

    @property
    def correct_option(self):
        return self.options.filter(is_correct=True).first()

    def flag_wrong_answer(self):
        """ผู้เรียนกดว่า 'ผมว่าเฉลยผิด' — พักข้อนี้ทันที ไม่รอให้ครบเกณฑ์

        ข้อหนึ่งข้อไม่มีค่าพอที่จะเสี่ยงสอนผิด
        """
        self.flagged_wrong_count += 1
        self.status = QuestionStatus.SUSPENDED
        self.save(update_fields=["flagged_wrong_count", "status", "updated_at"])


class DistractorType(models.TextChoices):
    """ทำไมตัวเลือกลวงตัวนี้ถึงลวงได้ — ใช้วิเคราะห์ว่าผู้เรียนพลาดแบบไหนซ้ำๆ"""
    NEAR_SYNONYM = "near_synonym", "คำใกล้เคียงความหมาย"
    SAME_CHAR = "same_char", "ใช้ตัวอักษรร่วมกัน"
    HOMOPHONE = "homophone", "เสียงเหมือน/ใกล้เคียง"
    WRONG_COLLOCATION = "wrong_collocation", "คำที่ไม่เข้าคู่กับคำข้างเคียง"
    PLAUSIBLE_FABRIC = "plausible_fabric", "สมเหตุสมผลแต่บทไม่ได้พูด"
    OVERGENERAL = "overgeneral", "กว้าง/เหมารวมเกินไป"

class QuestionOption(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="options", verbose_name="คำถาม",
    )
    text = models.CharField(max_length=400, verbose_name="ตัวเลือก")
    is_correct = models.BooleanField(default=False, verbose_name="เป็นคำตอบที่ถูก")
    distractor_type = models.CharField(
        max_length=24, choices=DistractorType.choices, blank=True, verbose_name="ชนิดตัวลวง",
    )
    rationale_th = models.CharField(max_length=400, blank=True, verbose_name="ทำไมผิด (ไทย)")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="ลำดับ")

    class Meta:
        verbose_name = "ตัวเลือก"
        verbose_name_plural = "ตัวเลือก"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{'✓' if self.is_correct else '✗'} {self.text[:40]}"
