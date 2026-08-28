"""ตัวประสานระหว่างชุดข้อสอบกับหน้าเว็บ — สร้างเซสชัน ส่งข้อถัดไป รับคำตอบ

ตรรกะการ *เลือก* ข้ออยู่ใน selection.py และตรรกะ *ตารางทบทวน* อยู่ใน srs.py
ไฟล์นี้ทำหน้าที่เดียว: แปลงแผนที่ได้มาให้เป็นสิ่งที่หน้าเว็บถามทีละข้อได้
และบันทึกผลกลับเข้าทั้งสองระบบให้ครบ (ห้ามให้ view ทำเอง)
"""
from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from . import placement, reading, selection, srs
from .models import (
    AnswerRecord, Card, DrillSession, ErrorCode, ErrorLog, Question,
    QuestionOption, Rating, Section,
)


@dataclass
class DrillQuestion:
    """หนึ่งข้อที่พร้อมแสดงบนหน้าเว็บ"""
    kind: str                 # "vocab" | "question"
    index: int
    total: int
    source: str               # due / wrong / new / filler
    prompt: str
    prompt_sub: str
    instruction: str
    choices: list[str]
    answer: str
    card_id: int | None = None
    question_id: int | None = None
    section: str = Section.VOCAB
    # บทอ่านของข้อนี้ — ว่างสำหรับข้อคำศัพท์ ดู reading.py
    passage_html: str = ""
    blank_no: int | None = None
    total_blanks: int = 0
    answers_whole_passage: bool = False


# ป้ายบอกว่าทำไมข้อนี้ถึงโผล่มาในชุดวันนี้ — เขียนด้วยภาษาผู้เรียน ไม่ใช่ภาษาระบบ
SOURCE_LABEL = {
    "due": "ถึงเวลาทวน",
    "wrong": "เคยตอบผิด",
    "new": "คำใหม่วันนี้",
    "filler": "ทวนเสริม",
}
SOURCE_WHY = {
    "due": "ระบบคำนวณว่าวันนี้คือวันที่ใกล้จะลืมคำนี้ที่สุด",
    "wrong": "เคยตอบผิดมาก่อน เลยเอากลับมาถามซ้ำจนกว่าจะแม่น",
    "new": "คำใหม่ตามโควตาของวันนี้",
    "filler": "ของถึงกำหนดทวนมีไม่ครบชุด เลยเติมข้อที่ทวนไว้ก็ดี",
}


def today_session(learner, *, today=None) -> DrillSession | None:
    """ชุดของวันนี้ (ถ้ามี) — หนึ่งวันมีได้ชุดเดียวเท่านั้น"""
    today = today or timezone.localdate()
    return (
        DrillSession.objects
        .filter(learner=learner, started_at__date=today)
        .order_by("-started_at")
        .first()
    )


def start_or_resume(learner, *, size: int | None = None) -> tuple[DrillSession, bool]:
    """คืนชุดของวันนี้ — สร้างใหม่ถ้ายังไม่มี ทำต่อถ้าค้างอยู่

    กฎหนึ่งวันหนึ่งชุดบังคับที่นี่ ไม่ใช่ที่หน้าเว็บ เพราะถ้าบังคับแค่ด้วยการซ่อนปุ่ม
    การกดปุ่มย้อนกลับหรือพิมพ์ URL ตรงๆ ก็สร้างชุดที่สองได้ แล้วสถิติจะเพี้ยน:
    ความแม่นถูกเฉลี่ยข้ามชุด จำนวนวันที่ทำติดกันนับผิด และการ์ดถูกทบทวนถี่เกินจริง
    """
    existing = today_session(learner)
    if existing:
        return existing, False

    plan = selection.build_daily_drill(learner, size=size)
    queue = [
        {"kind": "vocab" if it.card else "question",
         "id": it.card.pk if it.card else it.question.pk,
         "source": it.source}
        for it in plan.items
    ]
    session = DrillSession.objects.create(
        learner=learner,
        planned_size=plan.mix.get("requested", plan.size),
        mix=plan.mix, queue=queue, position=0,
    )
    return session, True


def current_entry(session: DrillSession) -> dict | None:
    """รายการที่กำลังทำอยู่ตามตำแหน่งที่บันทึกไว้ในฐานข้อมูล"""
    queue = session.queue or []
    if session.position >= len(queue):
        return None
    return queue[session.position]


def advance(session: DrillSession) -> None:
    session.position = min(session.position + 1, len(session.queue or []))
    session.save(update_fields=["position", "updated_at"])


def build_question(entry: dict, index: int, total: int) -> DrillQuestion | None:
    """แปลงหนึ่งรายการในคิวให้เป็นคำถามที่แสดงได้"""
    if entry["kind"] == "vocab":
        card = Card.objects.filter(pk=entry["id"]).select_related("vocab").first()
        if not card:
            return None
        q = placement.make_question(card.vocab)
        return DrillQuestion(
            kind="vocab", index=index, total=total, source=entry["source"],
            prompt=card.vocab.hanzi, prompt_sub=card.vocab.pinyin,
            instruction="เลือกความหมายที่ถูกต้อง",
            choices=q.choices, answer=q.answer, card_id=card.pk, section=Section.VOCAB,
        )

    question = Question.objects.filter(pk=entry["id"]).first()
    if not question:
        return None
    options = list(question.options.all().order_by("order", "id"))
    if not options:
        return None  # ข้อที่ยังไม่มีหน้าจอรองรับ (เรียงคำ / เรียงความ) — ข้ามไปข้อถัดไป
    correct = next((o.text for o in options if o.is_correct), question.answer_text)
    view = reading.build(question)
    return DrillQuestion(
        kind="question", index=index, total=total, source=entry["source"],
        prompt=view.prompt, prompt_sub="",
        instruction=view.instruction,
        choices=[o.text for o in options], answer=correct,
        question_id=question.pk, section=question.section,
        passage_html=view.passage_html, blank_no=view.blank_no,
        total_blanks=view.total_blanks,
        answers_whole_passage=view.answers_whole_passage,
    )


def _rating_for(is_correct: bool, elapsed_ms: int) -> int:
    """แปลงถูก/ผิด + เวลาที่ใช้ เป็นคะแนนของตัวจัดตาราง

    ตอบถูกแต่ช้ากว่า 12 วินาที = ยังไม่แน่นจริง ให้ HARD เพื่อให้กลับมาถามเร็วขึ้น
    ซึ่งตรงกับข้อสอบจริงที่มีเวลาจำกัด — จำได้แต่ช้าเกินไปก็ทำข้อสอบไม่ทัน
    """
    if not is_correct:
        return Rating.AGAIN
    if elapsed_ms and elapsed_ms > 12_000:
        return Rating.HARD
    return Rating.GOOD


def submit(session: DrillSession, entry: dict, given: str, correct_answer: str,
           *, elapsed_ms: int = 0, error_code: str = "") -> dict:
    """บันทึกคำตอบหนึ่งข้อ — เขียนครบทั้ง AnswerRecord, SRS และ ErrorLog"""
    is_correct = (given or "").strip() == (correct_answer or "").strip()
    card = Card.objects.filter(pk=entry["id"]).select_related("vocab").first() if entry["kind"] == "vocab" else None
    question = Question.objects.filter(pk=entry["id"]).first() if entry["kind"] == "question" else None

    AnswerRecord.objects.create(
        session=session, question=question, card=card, given=given[:400],
        is_correct=is_correct, elapsed_ms=elapsed_ms, error_code=error_code or "",
    )
    session.answered += 1
    session.correct += int(is_correct)
    session.save(update_fields=["answered", "correct", "updated_at"])

    if card:
        srs.review(card, _rating_for(is_correct, elapsed_ms), elapsed_ms=elapsed_ms)

    wrong_reason = ""
    if not is_correct:
        label = card.vocab.hanzi if card else (question.prompt_zh[:60] if question else given[:60])
        code = error_code or (ErrorCode.VOCAB if card else ErrorCode.MEANING)
        ErrorLog.record(
            session.learner, code, label,
            section=(Section.VOCAB if card else (question.section if question else Section.READING)),
            vocab=card.vocab if card else (question.vocab if question else None),
            question=question,
        )
        wrong_reason = ErrorCode.advice(code)
    elif card:
        # ตอบถูกแล้วก็ปิดบันทึกข้อผิดเดิมของคำนั้น ไม่ให้ตามตื้อคำที่แก้ได้แล้ว
        ErrorLog.objects.filter(
            learner=session.learner, vocab=card.vocab, resolved_at__isnull=True,
        ).update(resolved_at=timezone.now())

    # เหตุผลว่าตัวลวงแต่ละตัวผิดเพราะอะไร — ชั้นที่ 2 ของการ์ดเฉลย
    distractors = []
    if question and not is_correct:
        distractors = [
            o for o in question.options.filter(is_correct=False).order_by("order", "id")
            if o.rationale_th
        ]

    return {
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "advice": wrong_reason,
        "vocab": card.vocab if card else None,
        "question": question,
        "distractors": distractors,
    }


def finish(session: DrillSession) -> DrillSession:
    session.finished_at = timezone.now()
    session.save(update_fields=["finished_at", "updated_at"])
    return session
