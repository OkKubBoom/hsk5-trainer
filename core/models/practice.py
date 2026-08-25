"""การฝึกจริง — เซสชันรายวัน คำตอบ สรุปรายวัน ข้อสอบจำลอง งานเขียน"""
from django.db import models

from .base import ErrorCode, Section, TimeStamped
from .content import AudioClip, Question
from .lexicon import ExamSpec, WritingTemplate
from .srs import Card
from .users import LearnerProfile


class DrillSession(TimeStamped):
    """หนึ่งครั้งที่ผู้เรียนกดปุ่ม 'พร้อมทำข้อสอบ'"""
    learner = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="sessions", verbose_name="ผู้เรียน",
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="เริ่ม")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="จบ")

    planned_size = models.PositiveSmallIntegerField(default=40, verbose_name="จำนวนข้อที่วางไว้")
    answered = models.PositiveSmallIntegerField(default=0, verbose_name="ตอบไปแล้ว")
    correct = models.PositiveSmallIntegerField(default=0, verbose_name="ถูก")
    mix = models.JSONField(
        default=dict, blank=True, verbose_name="ส่วนผสมที่ใช้จริง",
        help_text='เช่น {"due": 20, "wrong": 12, "new": 8} — เก็บไว้เพื่อย้อนดูว่าวันนั้นระบบเลือกยังไง',
    )

    class Meta:
        verbose_name = "เซสชันฝึก"
        verbose_name_plural = "เซสชันฝึก"
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["learner", "-started_at"])]

    def __str__(self):
        return f"{self.learner.user} · {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def accuracy(self):
        return (self.correct / self.answered) if self.answered else None

    @property
    def minutes(self):
        end = self.finished_at or self.updated_at
        return max(0, int((end - self.started_at).total_seconds() // 60))


class AnswerRecord(models.Model):
    session = models.ForeignKey(
        DrillSession, on_delete=models.CASCADE, related_name="answers", verbose_name="เซสชัน",
    )
    question = models.ForeignKey(
        Question, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="answers", verbose_name="คำถาม",
    )
    card = models.ForeignKey(
        Card, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="answers", verbose_name="การ์ด",
    )
    given = models.CharField(max_length=400, blank=True, verbose_name="คำตอบที่ให้")
    is_correct = models.BooleanField(default=False, db_index=True, verbose_name="ถูก")
    elapsed_ms = models.PositiveIntegerField(default=0, verbose_name="ใช้เวลา (มิลลิวินาที)")
    error_code = models.CharField(
        max_length=16, choices=ErrorCode.choices, blank=True, db_index=True,
        verbose_name="สาเหตุที่ผิด",
        help_text="ผู้เรียนเป็นคนติดป้ายเอง — นี่คือข้อมูลที่มีค่าที่สุดของทั้งระบบ",
    )
    answered_at = models.DateTimeField(auto_now_add=True, verbose_name="เวลาที่ตอบ")

    class Meta:
        verbose_name = "คำตอบ"
        verbose_name_plural = "คำตอบ"
        ordering = ["id"]

    def __str__(self):
        return f"{'✓' if self.is_correct else '✗'} {self.given[:30]}"


class DailyRecord(models.Model):
    """สรุปรายวันหนึ่งแถวต่อผู้เรียนต่อวัน — ใช้วาดกราฟและคำนวณความสม่ำเสมอ

    คำนวณสดจาก AnswerRecord ทุกครั้งก็ได้ แต่ 110 วัน × 40 ข้อ = ช้าเกินจำเป็น
    """
    learner = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="daily_records", verbose_name="ผู้เรียน",
    )
    date = models.DateField(db_index=True, verbose_name="วันที่")
    answered = models.PositiveSmallIntegerField(default=0, verbose_name="ตอบไปกี่ข้อ")
    correct = models.PositiveSmallIntegerField(default=0, verbose_name="ถูกกี่ข้อ")
    minutes = models.PositiveSmallIntegerField(default=0, verbose_name="นาทีที่ใช้")
    new_words = models.PositiveSmallIntegerField(default=0, verbose_name="คำใหม่วันนี้")
    cumulative_words = models.PositiveIntegerField(default=0, verbose_name="คำสะสม")
    met_goal = models.BooleanField(default=False, verbose_name="ถึงเป้าของวัน")

    class Meta:
        verbose_name = "สรุปรายวัน"
        verbose_name_plural = "สรุปรายวัน"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["learner", "date"], name="uniq_daily_learner_date"),
        ]

    def __str__(self):
        return f"{self.learner.user} · {self.date}"

    @property
    def accuracy(self):
        return (self.correct / self.answered) if self.answered else None


class MockExam(TimeStamped):
    """ข้อสอบจำลองเต็มฉบับ — สัปดาห์ละครั้ง ไม่ใช่ทุกวัน

    ทำถี่เกินไปคือการวัดความล้า ไม่ใช่วัดความรู้
    """
    learner = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="mock_exams", verbose_name="ผู้เรียน",
    )
    spec = models.ForeignKey(
        ExamSpec, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="mock_exams", verbose_name="สเปกข้อสอบ",
    )
    taken_on = models.DateField(db_index=True, verbose_name="วันที่ทำ")
    paper_ref = models.CharField(
        max_length=64, blank=True, verbose_name="ชุดข้อสอบ", help_text="เช่น H51001",
    )
    is_timed = models.BooleanField(default=True, verbose_name="จับเวลาจริง")

    listening = models.PositiveSmallIntegerField(default=0, verbose_name="ฟัง")
    reading = models.PositiveSmallIntegerField(default=0, verbose_name="อ่าน")
    writing = models.PositiveSmallIntegerField(default=0, verbose_name="เขียน")
    notes = models.TextField(blank=True, verbose_name="บันทึก")

    class Meta:
        verbose_name = "ข้อสอบจำลอง"
        verbose_name_plural = "ข้อสอบจำลอง"
        ordering = ["-taken_on"]

    def __str__(self):
        return f"{self.learner.user} · {self.taken_on} · {self.total}"

    @property
    def total(self):
        return self.listening + self.reading + self.writing

    @property
    def passed(self):
        threshold = self.spec.pass_score if self.spec else 180
        return self.total >= threshold


class DictationAttempt(TimeStamped):
    """听写 — ฟังแล้วพิมพ์ แล้วเทียบทีละตัวอักษร

    ไม่มีเครื่องมือไหนในตลาดทำอันนี้สำหรับภาษาจีนพร้อมป้ายชนิดข้อผิดภาษาไทย
    นี่คือหนึ่งในไม่กี่อย่างที่คุ้มค่าสร้างเอง
    """
    learner = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="dictations", verbose_name="ผู้เรียน",
    )
    clip = models.ForeignKey(
        AudioClip, on_delete=models.CASCADE, related_name="dictations", verbose_name="ไฟล์เสียง",
    )
    typed_text = models.TextField(blank=True, verbose_name="ที่พิมพ์")
    char_diff = models.JSONField(
        default=list, blank=True, verbose_name="ผลเทียบตัวอักษร",
        help_text='เช่น [{"i": 3, "expected": "在", "got": "再", "type": "HOMOPHONE"}]',
    )
    accuracy_pct = models.FloatField(default=0, verbose_name="ความแม่น (%)")
    replay_count = models.PositiveSmallIntegerField(default=0, verbose_name="เปิดฟังซ้ำกี่ครั้ง")
    playback_rate = models.FloatField(default=1.0, verbose_name="ความเร็วที่ใช้ฟัง")

    class Meta:
        verbose_name = "การฝึก 听写"
        verbose_name_plural = "การฝึก 听写"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.clip} · {self.accuracy_pct:.0f}%"


class WritingSubmission(TimeStamped):
    learner = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="writings", verbose_name="ผู้เรียน",
    )
    prompt_zh = models.TextField(verbose_name="โจทย์")
    template = models.ForeignKey(
        WritingTemplate, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="submissions", verbose_name="เทมเพลตที่ใช้",
    )
    text_zh = models.TextField(verbose_name="งานเขียน")
    char_count = models.PositiveSmallIntegerField(default=0, verbose_name="จำนวนตัวอักษรจีน")
    minutes_spent = models.PositiveSmallIntegerField(default=0, verbose_name="นาทีที่ใช้")

    class Meta:
        verbose_name = "งานเขียนที่ส่ง"
        verbose_name_plural = "งานเขียนที่ส่ง"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.learner.user} · {self.char_count} ตัวอักษร"

    @property
    def meets_length(self):
        """ต่ำกว่า 80 ตัวอักษรถูกตัดคะแนนหนัก"""
        return self.char_count >= 80


class WritingFeedback(TimeStamped):
    submission = models.OneToOneField(
        WritingSubmission, on_delete=models.CASCADE, related_name="feedback", verbose_name="งานเขียน",
    )
    scores = models.JSONField(
        default=dict, verbose_name="คะแนนรายมิติ",
        help_text='{"content": 6, "grammar": 5, "vocabulary": 4, "coherence": 3, "form": 3}',
    )
    total_100 = models.PositiveSmallIntegerField(default=0, verbose_name="คะแนนเต็ม 100")
    issues = models.JSONField(
        default=list, blank=True, verbose_name="จุดผิดรายจุด",
        help_text='[{"wrong": "...", "right": "...", "why": "...", "kind": "grammar"}]',
    )
    graded_by = models.CharField(
        max_length=64, blank=True, verbose_name="ตรวจโดย",
        help_text="ชื่อโมเดล หรือชื่อครู",
    )

    class Meta:
        verbose_name = "ผลตรวจงานเขียน"
        verbose_name_plural = "ผลตรวจงานเขียน"

    def __str__(self):
        return f"{self.submission} → {self.total_100}/100"
