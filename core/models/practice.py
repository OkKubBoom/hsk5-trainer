"""การฝึกจริง — เซสชันรายวัน คำตอบ สรุปรายวัน ข้อสอบจำลอง งานเขียน"""
from datetime import timedelta

from django.db import models
from django.utils import timezone

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
    # คิวข้อสอบเก็บในฐานข้อมูล ไม่ใช่ใน session ของเบราว์เซอร์
    # เพื่อให้ปิดเครื่องแล้วกลับมาทำต่อจากข้อเดิมได้ และเปลี่ยนเครื่องก็ยังต่อได้
    queue = models.JSONField(
        default=list, blank=True, verbose_name="คิวข้อที่ล็อกไว้",
        help_text='เช่น [{"kind": "vocab", "id": 12, "source": "due"}]',
    )
    position = models.PositiveSmallIntegerField(default=0, verbose_name="ทำถึงข้อที่")

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
    def is_finished(self):
        return self.finished_at is not None

    @property
    def remaining(self):
        return max(0, len(self.queue or []) - self.position)

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

    # ── ทำในระบบ (ไม่ใช่กรอกคะแนนจากกระดาษ) ──
    # เก็บชุดคำถามไว้กับตัวสอบ เพื่อให้ทำต่อได้เมื่อปิดเบราว์เซอร์ และย้อนดูได้ว่าเจอข้อไหนบ้าง
    section = models.CharField(
        max_length=16, choices=Section.choices, blank=True, verbose_name="พาร์ทที่จำลอง",
    )
    queue = models.JSONField(default=list, blank=True, verbose_name="ชุดคำถาม")
    answers = models.JSONField(
        default=dict, blank=True, verbose_name="คำตอบที่เลือก",
        help_text='{"<question_id>": "ข้อความตัวเลือก"}',
    )
    flagged = models.JSONField(default=list, blank=True, verbose_name="ข้อที่ปักธง")
    started_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="เริ่มทำ")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="ส่งเมื่อ")
    time_limit_minutes = models.PositiveSmallIntegerField(default=45, verbose_name="เวลาที่ให้ (นาที)")
    correct_count = models.PositiveSmallIntegerField(default=0, verbose_name="ตอบถูกกี่ข้อ")
    auto_submitted = models.BooleanField(default=False, verbose_name="หมดเวลาแล้วส่งอัตโนมัติ")

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
    def is_full_exam(self):
        """วัดครบทั้งสามพาร์ทหรือยัง

        ระบบยังจำลองได้แค่พาร์ทอ่าน (core/mock.py เขียนเฉพาะ reading)
        คะแนนรวมจึงไม่มีทางถึง 180 ได้เลยไม่ว่าจะทำดีแค่ไหน
        """
        return bool(self.listening and self.writing)

    @property
    def passed(self):
        """ผ่านเกณฑ์ไหม — คืน None ถ้ายังวัดไม่ครบสามพาร์ท

        เดิมคืน False เสมอเมื่อวัดแค่พาร์ทอ่าน ซึ่งอ่านได้ว่า "สอบตก"
        ทั้งที่ความจริงคือ "ยังวัดไม่ครบ" — คนละความหมายกันคนละเรื่อง
        และเป็นตัวเลขที่จะถูกใช้ตัดสินใจว่าสมัครสอบรอบไหน
        """
        if not self.is_full_exam:
            return None
        threshold = self.spec.pass_score if self.spec else 180
        return self.total >= threshold

    # ── สำหรับข้อสอบจำลองที่ทำในระบบ ──

    @property
    def question_count(self):
        return len(self.queue or [])

    @property
    def answered_count(self):
        return len(self.answers or {})

    @property
    def is_running(self):
        return bool(self.started_at) and not self.finished_at

    @property
    def deadline(self):
        if not self.started_at:
            return None
        return self.started_at + timedelta(minutes=self.time_limit_minutes)

    @property
    def seconds_left(self):
        if not self.deadline:
            return 0
        return max(0, int((self.deadline - timezone.now()).total_seconds()))

    @property
    def is_expired(self):
        return self.is_running and self.seconds_left <= 0

    @property
    def score_percent(self):
        if not self.question_count:
            return None
        return round(self.correct_count / self.question_count * 100)

    @property
    def minutes_used(self):
        if not (self.started_at and self.finished_at):
            return None
        return max(1, round((self.finished_at - self.started_at).total_seconds() / 60))


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


class ReviewMode(models.TextChoices):
    """รูปแบบการถามในโหมดทบทวนอิสระ — เรียงจากง่ายไปยาก

    ขั้นที่ยากกว่าใกล้ข้อสอบจริงมากกว่า: การเห็นคำแล้วนึกความหมายออก
    ไม่ได้แปลว่าเห็นความหมายแล้วจะนึกคำออก ซึ่งเป็นทักษะที่พาร์ทเขียนต้องใช้
    """
    MEANING = "meaning", "เห็นตัวอักษร → เลือกความหมาย"
    HANZI = "hanzi", "เห็นความหมาย → เลือกตัวอักษร"


class ReviewPhase(models.TextChoices):
    """สองขั้นของหนึ่งรอบ — ดูก่อน แล้วค่อยทดสอบ

    ขั้น 'ดู' มีอยู่เพราะการทดสอบคำที่ยังไม่ได้ทบทวนคือการ *วัดผล* ไม่ใช่การ *ฝึก*
    ผู้เรียนต้องได้เห็นคำพร้อมความหมายก่อน แล้วจึงกดเองว่าพร้อม
    ช่องว่างระหว่างสองขั้นนี้คือสิ่งที่ทำให้ตัวเลขความแม่นมีความหมาย
    """
    STUDY = "study", "กำลังดูคำ"
    TEST = "test", "กำลังทดสอบ"


class ReviewSession(TimeStamped):
    """หนึ่งครั้งที่ผู้เรียนกดทบทวนเองนอกชุดฝึกรายวัน

    ตั้งใจแยกจาก DrillSession และ *ไม่* เลื่อนตารางทบทวนของ SRS
    เพราะถ้าทบทวนคำเดิมสิบรอบในวันเดียวแล้วเลื่อนตารางทุกรอบ ตัวจัดตารางจะเข้าใจว่า
    ผู้เรียนจำแม่นแล้วทั้งที่เพิ่งเห็นไปเมื่อครู่ แล้วนัดครั้งถัดไปไกลเกินจริง
    = การทิ้งคำนั้นโดยไม่ตั้งใจ

    แต่ "ตอบผิด" ยังถูกบันทึกเข้า ErrorLog เพราะนั่นคือสัญญาณจริง
    ชุดฝึกวันถัดไปมีโควตา 30% ให้คำที่เคยผิดอยู่แล้ว มันจะถูกหยิบไปเองอัตโนมัติ
    """
    learner = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="review_sessions",
        verbose_name="ผู้เรียน",
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="เริ่ม")
    studied_at = models.DateTimeField(null=True, blank=True, verbose_name="กดว่าจำเสร็จแล้วเมื่อ")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="จบ")

    phase = models.CharField(
        max_length=8, choices=ReviewPhase.choices, default=ReviewPhase.STUDY,
        verbose_name="อยู่ขั้นไหน",
    )
    mode = models.CharField(
        max_length=16, choices=ReviewMode.choices, default=ReviewMode.MEANING,
        verbose_name="รูปแบบการถาม",
    )
    scope = models.JSONField(
        default=dict, blank=True, verbose_name="เงื่อนไขที่เลือก",
        help_text='เช่น {"tier": "fresh", "window": 7, "level": 5} — เก็บไว้ให้ย้อนดูได้ว่าทบทวนอะไรไป',
    )
    queue = models.JSONField(default=list, blank=True, verbose_name="คิวการ์ดที่ล็อกไว้")
    position = models.PositiveSmallIntegerField(default=0, verbose_name="ทำถึงข้อที่")
    answered = models.PositiveSmallIntegerField(default=0, verbose_name="ตอบไปแล้ว")
    correct = models.PositiveSmallIntegerField(default=0, verbose_name="ถูก")

    class Meta:
        verbose_name = "ทบทวนอิสระ"
        verbose_name_plural = "ทบทวนอิสระ"
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["learner", "-started_at"])]

    def __str__(self):
        return f"ทบทวน {self.answered}/{len(self.queue or [])} ข้อ"

    @property
    def size(self):
        return len(self.queue or [])

    @property
    def is_running(self):
        return self.finished_at is None

    @property
    def in_study(self):
        return self.finished_at is None and self.phase == ReviewPhase.STUDY

    @property
    def wrong(self):
        return max(0, self.answered - self.correct)

    @property
    def accuracy(self):
        return round(self.correct / self.answered * 100) if self.answered else 0


class WordOrderAttempt(TimeStamped):
    """หนึ่งครั้งที่ผู้เรียนลองเรียงประโยค

    เดิมการฝึกเรียงคำไม่ถูกบันทึกเป็นงานเลย บันทึกเฉพาะตอนตอบผิดผ่าน ErrorLog
    ผู้เรียนที่ฝึกเรียงคำทั้งวันจึงขึ้นในหน้ากลุ่มว่า "เข้าระบบแต่ไม่ได้ทำอะไร"
    ทั้งที่ 书写第一部分 คือ 8 ข้อจาก 10 ของพาร์ทเขียน
    """
    learner = models.ForeignKey(
        LearnerProfile, on_delete=models.CASCADE, related_name="word_order_attempts",
        verbose_name="ผู้เรียน",
    )
    question = models.ForeignKey(
        Question, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="word_order_attempts", verbose_name="ข้อที่ทำ",
    )
    is_correct = models.BooleanField(default=False, verbose_name="เรียงถูก")

    class Meta:
        verbose_name = "ครั้งที่ฝึกเรียงคำ"
        verbose_name_plural = "ครั้งที่ฝึกเรียงคำ"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["learner", "-created_at"])]

    def __str__(self):
        return f"{self.learner} · {'ถูก' if self.is_correct else 'ผิด'}"
