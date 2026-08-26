"""ตรรกะแบบวัดระดับ — สุ่มคำ ตรวจคำตอบ และแปลผลเป็นค่าตั้งต้นของผู้เรียน

อยู่แยกจาก view ตามกฎของโปรเจกต์ (CLAUDE.md ข้อ 11) เพราะนี่คือตรรกะที่
ผิดแล้วเงียบ — ถ้าแปลผลพลาด ผู้เรียนจะได้โควตาคำใหม่ที่ผิดไปทั้งเทอม
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from .models import PlacementAnswer, PlacementTest, VocabItem

# สัดส่วนคำที่หยิบมาถามในแต่ละระดับ — เน้นระดับ 4-5 เพราะเป็นช่วงที่ตัดสินว่า
# ผู้เรียนพร้อมสอบ HSK5 หรือยัง ระดับ 1-2 ถามน้อยพอให้รู้ว่าพื้นไม่โหว่
LEVEL_WEIGHTS = {1: 0.05, 2: 0.05, 3: 0.15, 4: 0.35, 5: 0.40}

# เกณฑ์ตัดสินว่า "แน่นแล้ว" ในระดับหนึ่ง
SOLID_THRESHOLD = 0.85
SHAKY_THRESHOLD = 0.60


@dataclass
class PlacementQuestion:
    vocab: VocabItem
    choices: list[str]

    @property
    def answer(self):
        return self.vocab.meaning_th


def _pool(level: int):
    return VocabItem.objects.filter(hsk_level=level).exclude(meaning_th="")


def pick_words(size: int = 80, *, seed: int | None = None) -> list[VocabItem]:
    """เลือกคำที่จะถาม — ในแต่ละระดับหยิบจากคำที่พบบ่อยในข้อสอบก่อน

    ไม่สุ่มจากทั้งระดับเท่าๆ กัน เพราะคำที่ไม่เคยออกสอบเลยไม่ได้บอกอะไร
    เกี่ยวกับความพร้อมสอบ — หยิบจาก 60% แรกที่เรียงตามความสำคัญแล้วสุ่มในนั้น
    """
    rng = random.Random(seed)
    picked: list[VocabItem] = []
    for level, weight in LEVEL_WEIGHTS.items():
        want = max(1, round(size * weight))
        qs = _pool(level).order_by("frequency_rank", "hanzi")
        total = qs.count()
        if not total:
            continue
        head = list(qs[: max(want * 3, int(total * 0.6))])
        picked.extend(rng.sample(head, min(want, len(head))))
    rng.shuffle(picked)
    return picked[:size]


def make_question(vocab: VocabItem, *, seed: int | None = None) -> PlacementQuestion:
    """สร้างตัวเลือก 4 ตัว — ตัวลวงมาจากคำระดับเดียวกัน เพื่อให้ตัดตัวเลือกด้วย
    ความยากของคำไม่ได้ ต้องรู้ความหมายจริงถึงจะตอบถูก
    """
    rng = random.Random(seed if seed is not None else vocab.pk)
    distractors = list(
        _pool(vocab.hsk_level)
        .exclude(pk=vocab.pk)
        .exclude(meaning_th=vocab.meaning_th)
        .order_by("?")[:3]
        .values_list("meaning_th", flat=True)
    )
    if len(distractors) < 3:  # ระดับที่มีคำน้อย — ยืมจากระดับใกล้เคียง
        extra = (
            VocabItem.objects
            .filter(Q(hsk_level=vocab.hsk_level - 1) | Q(hsk_level=vocab.hsk_level + 1))
            .exclude(meaning_th="")
            .exclude(meaning_th=vocab.meaning_th)
            .order_by("?")[: 3 - len(distractors)]
            .values_list("meaning_th", flat=True)
        )
        distractors.extend(extra)
    choices = [vocab.meaning_th] + list(distractors)
    rng.shuffle(choices)
    return PlacementQuestion(vocab=vocab, choices=choices)


def start(learner, *, size: int = 80, seed: int | None = None) -> PlacementTest:
    test = PlacementTest.objects.create(learner=learner, planned_size=size)
    test.result = {"queue": [v.pk for v in pick_words(size, seed=seed)]}
    test.save(update_fields=["result", "updated_at"])
    return test


def next_vocab(test: PlacementTest) -> VocabItem | None:
    """คำถัดไปที่ยังไม่ได้ตอบ — อ่านจากคิวที่ล็อกไว้ตอนเริ่ม จึงรีเฟรชหน้าได้ไม่เพี้ยน"""
    queue = test.result.get("queue") or []
    answered = set(test.answers.values_list("vocab_id", flat=True))
    for pk in queue:
        if pk not in answered:
            return VocabItem.objects.filter(pk=pk).first()
    return None


def record(test: PlacementTest, vocab: VocabItem, given: str, *,
           said_unknown: bool = False, elapsed_ms: int = 0) -> PlacementAnswer:
    answer, _ = PlacementAnswer.objects.get_or_create(
        test=test, vocab=vocab,
        defaults={
            "hsk_level": vocab.hsk_level,
            "given": "" if said_unknown else given[:255],
            "is_correct": (not said_unknown) and given == vocab.meaning_th,
            "said_unknown": said_unknown,
            "elapsed_ms": elapsed_ms,
        },
    )
    return answer


def score(test: PlacementTest) -> dict:
    """แปลผลเป็นตัวเลขที่เอาไปตั้งค่าระบบได้จริง

    known_vocab_estimate คำนวณจากอัตราที่ตอบถูกในแต่ละระดับ คูณกับจำนวนคำ
    ทั้งหมดของระดับนั้นในลิสต์ทางการ ไม่ใช่จำนวนคำที่บังเอิญมีในฐานข้อมูล
    """
    by_level: dict[int, dict] = {}
    for ans in test.answers.all():
        row = by_level.setdefault(ans.hsk_level, {"asked": 0, "correct": 0, "unknown": 0})
        row["asked"] += 1
        row["correct"] += int(ans.is_correct)
        row["unknown"] += int(ans.said_unknown)

    official_size = {1: 150, 2: 150, 3: 300, 4: 600, 5: 1300}
    known_total = 0.0
    for level, row in by_level.items():
        row["rate"] = row["correct"] / row["asked"] if row["asked"] else 0.0
        row["verdict"] = (
            "แน่นแล้ว" if row["rate"] >= SOLID_THRESHOLD
            else "ยังไม่แน่น" if row["rate"] >= SHAKY_THRESHOLD
            else "ต้องเริ่มจากตรงนี้"
        )
        known_total += row["rate"] * official_size.get(level, 0)

    # ระดับที่ควรเริ่มป้อนคำใหม่ = ระดับต่ำสุดที่ยังไม่แน่น
    start_level = 5
    for level in sorted(by_level):
        if by_level[level]["rate"] < SOLID_THRESHOLD:
            start_level = level
            break

    remaining = max(0, 2500 - round(known_total))
    days = max(1, (test.learner.target_exam_date - timezone.localdate()).days)
    # เผื่อเวลาไว้ 20% สำหรับช่วง freeze และวันที่ทำไม่ไหว
    usable_days = max(1, int(days * 0.8))
    suggested_new = max(5, min(30, -(-remaining // usable_days)))

    return {
        "by_level": {str(k): v for k, v in sorted(by_level.items())},
        "known_vocab_estimate": round(known_total),
        "remaining_to_2500": remaining,
        "start_level": start_level,
        "days_to_exam": days,
        "suggested_new_words_per_day": suggested_new,
        "answered": test.answers.count(),
        "unknown_pressed": sum(r["unknown"] for r in by_level.values()),
    }


def finish(test: PlacementTest) -> dict:
    """ปิดแบบวัดระดับ แล้วเขียนค่าที่ได้ลงโปรไฟล์ผู้เรียน"""
    result = score(test)
    queue = test.result.get("queue")
    test.result = {**result, "queue": queue}
    test.finish()
    test.save(update_fields=["result", "updated_at"])

    learner = test.learner
    learner.known_vocab_estimate = result["known_vocab_estimate"]
    learner.new_words_per_day = result["suggested_new_words_per_day"]
    learner.save(update_fields=["known_vocab_estimate", "new_words_per_day", "updated_at"])
    return result
