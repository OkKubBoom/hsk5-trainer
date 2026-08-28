"""ทบทวนอิสระ — ผู้เรียนเลือกเองว่าจะทวนคำกลุ่มไหน กี่ข้อ ถามแบบไหน

ต่างจากชุดฝึกรายวันโดยตั้งใจ:

    ชุดฝึกรายวัน  ระบบเลือกให้ · วันละครั้ง · เลื่อนตารางทบทวน · นับใน streak
    ทบทวนอิสระ    ผู้เรียนเลือกเอง · กี่ครั้งก็ได้ · ไม่เลื่อนตาราง · ไม่นับใน streak

หนึ่งรอบมีสองขั้นเสมอ: **ดูคำก่อน แล้วกดเองว่าพร้อม จึงเริ่มทดสอบ**
ถ้าโยนคำถามใส่ทันทีโดยไม่ให้ดูก่อน สิ่งที่วัดได้คือความจำเดิม ไม่ใช่ผลของการทบทวน
และผู้เรียนจะเห็นแต่คะแนนต่ำโดยไม่รู้ว่าต้องทำอะไรถึงจะดีขึ้น

เหตุผลที่ห้ามเลื่อนตารางทบทวน (สำคัญที่สุดในไฟล์นี้):
SM-2 อ่านค่า "ตอบถูก" ว่าเป็นหลักฐานว่าความจำอยู่ได้นานขึ้น แล้วขยายระยะห่าง
แต่ตอบถูกเพราะเพิ่งเห็นคำนั้นไปเมื่อสองนาทีก่อน ไม่ใช่หลักฐานอะไรเลย
ถ้านับรวม ระยะห่างจะพองจนนัดทบทวนครั้งหน้าเลยวันสอบ = ทิ้งคำนั้นโดยไม่รู้ตัว

แต่ "ตอบผิด" เชื่อถือได้เสมอ — ลืมก็คือลืม ไม่ว่าจะเพิ่งเห็นมาหรือไม่
จึงบันทึกเข้า ErrorLog ให้ชุดฝึกวันถัดไปหยิบไปเองผ่านโควตา 30% ที่มีอยู่แล้ว
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import (
    Card, CardState, ErrorCode, ErrorLog, Rating, ReviewMode, ReviewPhase,
    ReviewSession, Section, VocabItem,
)

SIZE_CHOICES = [10, 20, 30, 50]
DEFAULT_SIZE = 20

# ── แกนที่ 1: ระดับความแม่น ───────────────────────────────────────────
# แบ่งจากข้อมูลที่ตัวจัดตารางเขียนไว้อยู่แล้ว ไม่ต้องเพิ่มฟิลด์ใหม่
# เงื่อนไขต้องไม่ทับกัน มิฉะนั้นคำเดียวจะถูกนับสองระดับแล้วตัวเลขไม่ตรง
TIERS = {
    "unseen": {
        "label": "ยังไม่เคยเจอ",
        "hint": "คำใหม่ที่ยังไม่เคยถูกถาม — ดูก่อนแล้วลองทดสอบได้เลย",
        "filter": Q(reps=0),
    },
    "lapsed": {
        "label": "เคยจำได้แล้วลืม",
        "hint": "คำที่หลอกตัวเองว่าจำได้ — คุ้มที่สุดที่จะทวน",
        "filter": Q(reps__gte=1) & (Q(lapses__gte=1) | Q(state=CardState.LAPSED)),
    },
    "fresh": {
        "label": "เพิ่งเริ่มจำ",
        "hint": "ทบทวนไม่เกิน 2 ครั้ง ยังเปราะมาก",
        "filter": Q(reps__gte=1, lapses=0, interval_days__lt=3),
    },
    "growing": {
        "label": "เริ่มอยู่ตัว",
        "hint": "ผ่านมาแล้วหลายรอบ แต่ยังไม่แน่น",
        "filter": Q(reps__gte=1, lapses=0, interval_days__gte=3, interval_days__lt=15),
    },
    "solid": {
        "label": "จำได้แน่น",
        "hint": "ทวนไว้กันหลุด",
        "filter": Q(reps__gte=1, lapses=0, interval_days__gte=15, interval_days__lt=45),
    },
    "mastered": {
        "label": "แม่นแล้ว",
        "hint": "เอาไว้สร้างความมั่นใจก่อนสอบ",
        "filter": Q(reps__gte=1, lapses=0, interval_days__gte=45),
    },
}

# ── แกนที่ 2: ช่วงเวลา ────────────────────────────────────────────────
# ทวนของเมื่อวานคุ้มที่สุด เพราะการลืมเกิดหนักที่สุดใน 24-48 ชม.แรก
WINDOWS = {
    0: "ทุกช่วงเวลา",
    1: "ที่จำถูกเมื่อวาน",
    7: "ที่จำถูกใน 7 วัน",
    30: "ที่จำถูกใน 30 วัน",
}


@dataclass
class ReviewQuestion:
    """หนึ่งข้อที่พร้อมแสดงบนหน้าเว็บ"""
    index: int
    total: int
    mode: str
    prompt: str
    prompt_sub: str
    instruction: str
    choices: list[str]
    answer: str
    card_id: int
    vocab: VocabItem


def learned_cards(learner):
    """ฐานของทุกตัวกรองในหน้านี้ — รวมคำใหม่ที่ยังไม่เคยเจอด้วย

    เดิมกรอง reps >= 1 ออกไป ด้วยเหตุผลว่า "ทบทวน ไม่ใช่เรียนใหม่"
    แต่นั่นทำให้ผู้เรียนที่เพิ่งเริ่มเปิดหน้านี้มาแล้วเจอ 2 คำ ซึ่งใช้ทำอะไรไม่ได้
    และเหตุผลเดิมก็ผิดด้วย — โหมดนี้มีขั้น 'ดูคำก่อน' อยู่แล้ว
    ซึ่งเหมาะกับคำใหม่ยิ่งกว่าคำเก่า

    การหยิบคำใหม่มาดูที่นี่ไม่กระทบตารางทบทวน คำนั้นยังคงสถานะ new
    และจะถูกชุดฝึกรายวันหยิบไปสอนตามโควตา 20% ตามปกติ
    """
    return (
        Card.objects
        .filter(learner=learner)
        .exclude(state=CardState.SUSPENDED)
        .select_related("vocab")
    )


def _apply_window(qs, window: int, *, today=None):
    """กรองเหลือเฉพาะการ์ดที่ 'ตอบถูก' ในช่วงเวลาที่เลือก

    ใช้ rating >= GOOD ไม่ใช่แค่ 'มีบันทึก' เพราะคำที่ตอบผิดเมื่อวาน
    ไม่ใช่ 'คำที่จำได้เมื่อวาน' — มันคือคำที่ควรอยู่ในกองอื่น
    """
    if not window:
        return qs
    today = today or timezone.localdate()
    if window == 1:
        start = end = today - timedelta(days=1)
    else:
        start, end = today - timedelta(days=window), today
    return qs.filter(
        reviews__rating__gte=Rating.GOOD,
        reviews__reviewed_at__date__gte=start,
        reviews__reviewed_at__date__lte=end,
    ).distinct()


def build_pool(learner, *, tier: str = "", window: int = 0, level: int = 0, today=None):
    """รวมทั้งสามแกนเข้าด้วยกัน — ตัวกรองที่ไม่ได้เลือกจะไม่ถูกใช้"""
    qs = learned_cards(learner)
    if tier in TIERS:
        qs = qs.filter(TIERS[tier]["filter"])
    if level:
        qs = qs.filter(vocab__hsk_level=level)
    return _apply_window(qs, window, today=today)


def tier_counts(learner, *, window: int = 0, level: int = 0, today=None) -> list[dict]:
    """จำนวนคำในแต่ละระดับ ตามตัวกรองอื่นที่เลือกไว้แล้ว

    ต้องนับตามตัวกรองปัจจุบัน ไม่ใช่นับรวมทั้งคลัง มิฉะนั้นผู้ใช้จะเห็นเลข 300
    แล้วกดเข้าไปเจอ 4 คำ ซึ่งทำให้เลิกเชื่อตัวเลขบนหน้าจอ
    """
    base = _apply_window(learned_cards(learner), window, today=today)
    if level:
        base = base.filter(vocab__hsk_level=level)
    out = [{
        "key": "", "label": "ทุกกอง", "hint": "คำทั้งหมดในคลังของคุณ ทั้งที่เคยเจอและยังไม่เคยเจอ",
        "count": base.count(),
    }]
    for key, spec in TIERS.items():
        out.append({
            "key": key, "label": spec["label"], "hint": spec["hint"],
            "count": base.filter(spec["filter"]).count(),
        })
    return out


def level_counts(learner, *, window: int = 0, today=None) -> list[tuple[int, int]]:
    base = _apply_window(learned_cards(learner), window, today=today)
    return [(lv, base.filter(vocab__hsk_level=lv).count()) for lv in range(1, 7)]


# ── สร้างคำถาม ────────────────────────────────────────────────────────

def _distractors(vocab: VocabItem, field: str, n: int = 3) -> list[str]:
    """ตัวลวงจากคำระดับเดียวกัน — ถ้าคนละระดับจะเดาถูกด้วยความยากของคำ
    โดยไม่ต้องรู้ความหมายจริง ซึ่งวัดอะไรไม่ได้เลย
    """
    pool = (
        VocabItem.objects
        .filter(hsk_level=vocab.hsk_level)
        .exclude(pk=vocab.pk)
        .exclude(**{field: ""})
        .exclude(**{field: getattr(vocab, field)})
    )
    out = list(pool.order_by("?")[:n].values_list(field, flat=True))
    if len(out) < n:  # ระดับที่มีคำน้อย — ยืมจากระดับใกล้เคียง
        extra = (
            VocabItem.objects
            .filter(Q(hsk_level=vocab.hsk_level - 1) | Q(hsk_level=vocab.hsk_level + 1))
            .exclude(**{field: ""})
            .exclude(**{field: getattr(vocab, field)})
            .order_by("?")[: n - len(out)]
            .values_list(field, flat=True)
        )
        out.extend(extra)
    return out


def make_question(card: Card, mode: str, index: int, total: int,
                  *, seed: int | None = None) -> ReviewQuestion:
    vocab = card.vocab
    rng = random.Random(seed if seed is not None else card.pk)

    if mode == ReviewMode.HANZI:
        choices = [vocab.hanzi] + _distractors(vocab, "hanzi")
        rng.shuffle(choices)
        return ReviewQuestion(
            index=index, total=total, mode=mode,
            prompt=vocab.meaning_th, prompt_sub="",
            instruction="เลือกตัวอักษรที่ตรงกับความหมายนี้",
            choices=choices, answer=vocab.hanzi, card_id=card.pk, vocab=vocab,
        )

    choices = [vocab.meaning_th] + _distractors(vocab, "meaning_th")
    rng.shuffle(choices)
    return ReviewQuestion(
        index=index, total=total, mode=mode,
        prompt=vocab.hanzi, prompt_sub=vocab.pinyin,
        instruction="เลือกความหมายที่ถูกต้อง",
        choices=choices, answer=vocab.meaning_th, card_id=card.pk, vocab=vocab,
    )


# ── วงจรของหนึ่งรอบทบทวน ─────────────────────────────────────────────

def running(learner) -> ReviewSession | None:
    """รอบที่ยังทำค้างอยู่ — กลับมาทำต่อได้ ไม่ต้องเริ่มใหม่"""
    return (
        ReviewSession.objects
        .filter(learner=learner, finished_at__isnull=True)
        .order_by("-started_at")
        .first()
    )


def start(learner, *, tier: str = "", window: int = 0, level: int = 0,
          size: int = DEFAULT_SIZE, mode: str = ReviewMode.MEANING,
          seed: int | None = None, today=None) -> ReviewSession | None:
    """เริ่มรอบใหม่ — คืน None ถ้าไม่มีคำเข้าเงื่อนไขเลย

    ปิดรอบเก่าที่ค้างก่อน เพราะการมีสองรอบเปิดพร้อมกันทำให้ปุ่ม 'ทำต่อ'
    ชี้ไปคนละรอบกับที่ผู้ใช้เพิ่งกดสร้าง
    """
    pool = list(build_pool(learner, tier=tier, window=window, level=level, today=today)
                .values_list("pk", flat=True))
    if not pool:
        return None

    rng = random.Random(seed)
    rng.shuffle(pool)
    queue = pool[:size]

    stale = running(learner)
    if stale:
        finish(stale)

    return ReviewSession.objects.create(
        learner=learner, mode=mode, queue=queue, phase=ReviewPhase.STUDY,
        scope={"tier": tier, "window": window, "level": level, "size": len(queue)},
    )


def study_cards(session: ReviewSession) -> list[Card]:
    """คำทั้งชุดสำหรับขั้นดู — เรียงตามคิวที่ล็อกไว้ ไม่ใช่ตามฐานข้อมูล
    เพื่อให้ลำดับที่เห็นตอนดู ตรงกับลำดับที่จะถูกถาม
    """
    queue = session.queue or []
    by_pk = {c.pk: c for c in Card.objects.filter(pk__in=queue).select_related("vocab")}
    return [by_pk[pk] for pk in queue if pk in by_pk]


def begin_test(session: ReviewSession) -> ReviewSession:
    """ผู้เรียนกดว่าจำเสร็จแล้ว — ข้ามขั้นดูไปขั้นทดสอบ

    เมื่อข้ามมาแล้วห้ามย้อนกลับไปดูอีก มิฉะนั้นจะเปิดดูเฉลยกลางคันได้
    แล้วตัวเลขความแม่นจะไม่ได้วัดอะไรเลย
    """
    if session.phase == ReviewPhase.STUDY:
        session.phase = ReviewPhase.TEST
        session.studied_at = timezone.now()
        session.save(update_fields=["phase", "studied_at", "updated_at"])
    return session


def current_card(session: ReviewSession) -> Card | None:
    queue = session.queue or []
    if session.position >= len(queue):
        return None
    return Card.objects.filter(pk=queue[session.position]).select_related("vocab").first()


def advance(session: ReviewSession) -> None:
    session.position = min(session.position + 1, session.size)
    session.save(update_fields=["position", "updated_at"])


def submit(session: ReviewSession, card: Card, given: str, *, elapsed_ms: int = 0) -> dict:
    """บันทึกคำตอบหนึ่งข้อ

    จงใจไม่เรียก srs.review() — ดูเหตุผลที่หัวไฟล์
    """
    correct_answer = (
        card.vocab.hanzi if session.mode == ReviewMode.HANZI else card.vocab.meaning_th
    )
    is_correct = (given or "").strip() == (correct_answer or "").strip()

    session.answered += 1
    session.correct += int(is_correct)
    session.save(update_fields=["answered", "correct", "updated_at"])

    if not is_correct:
        ErrorLog.record(
            session.learner, ErrorCode.VOCAB, card.vocab.hanzi,
            section=Section.VOCAB, vocab=card.vocab,
        )

    return {
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "vocab": card.vocab,
        "advice": "" if is_correct else ErrorCode.advice(ErrorCode.VOCAB),
    }


def finish(session: ReviewSession) -> ReviewSession:
    session.finished_at = timezone.now()
    session.save(update_fields=["finished_at", "updated_at"])
    return session


def stats(learner, *, days: int = 7, today=None) -> dict:
    """สรุปการทบทวนอิสระ — แยกจากสถิติหลักโดยตั้งใจ ไม่ปนกับ streak"""
    today = today or timezone.localdate()
    done = ReviewSession.objects.filter(learner=learner, answered__gte=1)
    recent = done.filter(started_at__date__gte=today - timedelta(days=days))
    answered = sum(s.answered for s in recent)
    correct = sum(s.correct for s in recent)
    todays = list(done.filter(started_at__date=today))
    t_answered = sum(s.answered for s in todays)
    t_correct = sum(s.correct for s in todays)
    return {
        "rounds_total": done.count(),
        "rounds_recent": recent.count(),
        "answered_recent": answered,
        "accuracy_recent": round(correct / answered * 100) if answered else None,
        # วัดผลรายวัน — ตัวเลขชุดนี้แยกจาก streak และความแม่นของชุดฝึกหลัก
        "today_rounds": len(todays),
        "today_answered": t_answered,
        "today_correct": t_correct,
        "today_accuracy": round(t_correct / t_answered * 100) if t_answered else None,
        "history": list(done.order_by("-started_at")[:10]),
    }
