"""Daily Drill Engine — เลือกว่าวันนี้จะถามอะไร

กฎข้อเดียวที่สำคัญที่สุด: **ขนาดชุดคงที่ ส่วนผสมเปลี่ยน**

เจ้าของโปรเจกต์เสนอตอนแรกว่าให้เพิ่มจำนวนข้อวันละ 10% ทบต้น เพื่อให้
"ของเก่าไม่หาย" ซึ่งเป็นเจตนาที่ถูกต้อง แต่คณิตศาสตร์ไม่รอด:

    เริ่ม 10 ข้อ → วันที่ 21 = 68 ข้อ → วันที่ 33 = 211 ข้อ (ชนเพดาน 3.5 ชม.)
    → วันที่ 60 = 2,769 ข้อ → วันสอบ = 324,940 ข้อ

และเหตุผลที่หนักกว่าเรื่องเวลา: ข้อสอบจริงมี 100 ข้อใน 125 นาที
การซ้อมวันละ 663 ข้อไม่ได้ทำให้เก่งขึ้น มันแค่ทำให้เลิกล้ม

ทางออกคือตรึงเวลาไว้ แล้วให้อัลกอริทึมเลือกว่า *ข้อไหน* ควรออก
ระบบไม่ถามสิ่งที่จำแม่นแล้ว มันไปถามเฉพาะสิ่งที่กำลังจะลืม
ครอบคลุมเท่าเดิม แต่เวลาไม่บาน
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from . import reading, srs
from .models import Card, ErrorLog, LearnerProfile, Question, QuestionStatus


@dataclass
class DrillItem:
    """หนึ่งข้อในชุด — เป็นการ์ดคำศัพท์ หรือคำถามจากคลังก็ได้"""
    source: str                      # "due" | "wrong" | "new" | "filler"
    card: Card | None = None
    question: Question | None = None

    @property
    def key(self):
        if self.card_id_safe:
            return f"card:{self.card.pk}"
        return f"q:{self.question.pk}"

    @property
    def card_id_safe(self):
        return self.card.pk if self.card else None


@dataclass
class DrillPlan:
    items: list[DrillItem] = field(default_factory=list)
    mix: dict = field(default_factory=dict)

    @property
    def size(self):
        return len(self.items)


def _weekly_difficulty(learner, today=None) -> str:
    """ความยากโตตามสัปดาห์ แทนที่จะให้จำนวนข้อโต

    W1-4  ประโยคสั้น เวลาไม่บีบ
    W5-8  ความยาวเท่าข้อสอบจริง
    W9+   จับเวลาโหดกว่าจริง 10% เพื่อให้ห้องสอบรู้สึกช้าลง
    """
    left = srs.days_to_exam(learner, today)
    if left > 80:
        return "short"
    if left > 45:
        return "exam"
    return "exam_tight"


def _interleave(groups: list[list[DrillItem]], rng: random.Random) -> list[DrillItem]:
    """คละที่มาของข้อให้กระจายทั่วชุด ไม่ให้กองเป็นบล็อก

    การสลับชนิดข้อในเซสชันเดียว (interleaving) ทำให้รู้สึกยากกว่า
    และคะแนนซ้อมแย่กว่าการทำทีละกอง แต่จำได้นานกว่าและใช้จริงได้ดีกว่า
    ความรู้สึกว่า "วันนี้ทำได้แย่" จึงเป็นสัญญาณที่ถูก ไม่ใช่ปัญหา
    """
    pools = [g[:] for g in groups if g]
    out: list[DrillItem] = []
    while pools:
        weights = [len(p) for p in pools]
        idx = rng.choices(range(len(pools)), weights=weights, k=1)[0]
        out.append(pools[idx].pop(0))
        if not pools[idx]:
            pools.pop(idx)
    return out


def _cluster_groups(items: list[DrillItem]) -> list[DrillItem]:
    """ข้อที่มาจากบทอ่านเดียวกันต้องอยู่ติดกัน

    หนึ่งบทอ่านมี 3-4 คำถาม ถ้าปล่อยให้กระจายทั่วชุด ผู้เรียนต้องอ่านบทความ
    250 ตัวอักษรเดิมซ้ำสี่รอบในชุดเดียว ทั้งเปลืองเวลาและไม่เหมือนของจริง
    ข้อสอบจริงอ่านครั้งเดียวแล้วตอบรวด

    ไม่ขัดกับหลักคละพาร์ท (interleaving) เพราะสิ่งที่ต้องคละคือ *ชนิดของโจทย์*
    ไม่ใช่การฉีกคำถามของบทอ่านเดียวกันออกจากกัน
    """
    positions: dict[int, list[int]] = {}
    for i, it in enumerate(items):
        gid = it.question.group_id if it.question else None
        if gid:
            positions.setdefault(gid, []).append(i)

    def order_key(index: int):
        # เรียงตามเลขข้อในกระดาษจริง ให้ลำดับเหมือนตอนสอบ
        return (reading.blank_number(items[index].question) or 0, items[index].question.pk)

    out: list[DrillItem] = []
    taken: set[int] = set()
    for i, it in enumerate(items):
        if i in taken:
            continue
        out.append(it)
        taken.add(i)
        gid = it.question.group_id if it.question else None
        if not gid:
            continue
        siblings = sorted((j for j in positions[gid] if j not in taken), key=order_key)
        for j in siblings:
            out.append(items[j])
            taken.add(j)
    return out


def build_daily_drill(
    learner: LearnerProfile,
    *,
    now: datetime | None = None,
    size: int | None = None,
    seed: int | None = None,
) -> DrillPlan:
    """สร้างชุดข้อสอบประจำวันหนึ่งชุด

    สัดส่วนตั้งต้น 50% ถึงกำหนดทบทวน / 30% เคยผิด / 20% ของใหม่
    ถ้าส่วนไหนมีไม่พอ ส่วนที่ขาดจะถูกเติมด้วยการ์ดที่ใกล้ครบกำหนดที่สุด
    (ไม่ปล่อยให้ชุดเล็กลง เพราะขนาดคงที่คือสัญญาที่ให้ไว้กับผู้เรียน)
    """
    now = now or timezone.now()
    rng = random.Random(seed)
    size = size or learner.drill_size or settings.DRILL_DEFAULT_SIZE
    mix_cfg = settings.DRILL_MIX

    n_due = round(size * mix_cfg["due"])
    n_wrong = round(size * mix_cfg["wrong"])
    n_new = size - n_due - n_wrong

    max_questions = getattr(settings, "DRILL_MAX_QUESTIONS", size)

    used_cards: set[int] = set()
    used_questions: set[int] = set()

    # ── 50% ถึงกำหนดทบทวน ────────────────────────────────
    due_items = []
    for card in srs.due_queryset(learner, now)[:n_due]:
        due_items.append(DrillItem(source="due", card=card))
        used_cards.add(card.pk)

    # ── 30% เคยตอบผิด ────────────────────────────────────
    # เรียงในโค้ดไม่ใช่ใน SQL เพราะ priority_score ผสมความถี่กับความใหม่
    open_errors = list(
        ErrorLog.objects
        .filter(learner=learner, resolved_at__isnull=True)
        .select_related("vocab", "question")[:200]
    )
    open_errors.sort(key=lambda e: e.priority_score(now), reverse=True)

    wrong_items = []
    for err in open_errors:
        if len(wrong_items) >= n_wrong:
            break
        if err.vocab_id:
            card = (
                Card.objects
                .filter(learner=learner, vocab_id=err.vocab_id)
                .exclude(pk__in=used_cards)
                .select_related("vocab")
                .order_by("due_at")
                .first()
            )
            if card:
                wrong_items.append(DrillItem(source="wrong", card=card))
                used_cards.add(card.pk)
                continue
        if err.question_id and err.question_id not in used_questions:
            if len(used_questions) >= max_questions:
                continue  # เต็มเพดานข้อสอบจริงแล้ว ปล่อยให้คำศัพท์เข้าแทน
            q = err.question
            if q and q.status == QuestionStatus.ACTIVE:
                wrong_items.append(DrillItem(source="wrong", question=q))
                used_questions.add(q.pk)

    # ── 20% ของใหม่ (ผ่านตัวคุมโหลดแล้ว) ──────────────────
    # หนึ่งคำมีได้หลายการ์ด (อ่านได้ / ฟังออก) แต่ในเซสชันเดียว
    # คำใหม่คำหนึ่งควรโผล่ครั้งเดียว มิฉะนั้นโควตา 8 คำใหม่จะกลายเป็น 4 คำ ถามคำละสองรอบ
    quota = srs.new_quota_today(learner, now)
    used_new_vocabs: set[int] = set()
    new_items = []
    for card in srs.new_queryset(learner):
        if len(new_items) >= min(n_new, quota):
            break
        if card.vocab_id in used_new_vocabs:
            continue
        new_items.append(DrillItem(source="new", card=card))
        used_cards.add(card.pk)
        used_new_vocabs.add(card.vocab_id)

    # ── เติมให้ครบขนาด ───────────────────────────────────
    shortfall = size - (len(due_items) + len(wrong_items) + len(new_items))
    filler_items = []
    if shortfall > 0:
        near_due = (
            Card.objects
            .filter(learner=learner, due_at__isnull=False)
            .exclude(pk__in=used_cards)
            .select_related("vocab")
            .order_by("due_at")[:shortfall]
        )
        for card in near_due:
            filler_items.append(DrillItem(source="filler", card=card))
            used_cards.add(card.pk)
        shortfall = size - (len(due_items) + len(wrong_items) + len(new_items) + len(filler_items))

    # ยังขาดอยู่ → เติมด้วยคำถามจากคลังที่ยังไม่ได้ใช้
    if shortfall > 0:
        # เฉพาะข้อที่มีตัวเลือกให้กด — ข้อเรียงคำและข้อเขียนเรียงความยังไม่มีหน้าจอรองรับ
        # ถ้าปล่อยเข้ามาผู้เรียนจะเจอข้อที่ตอบไม่ได้จริง แล้วถูกนับว่าผิด
        room_for_questions = max(0, max_questions - len(used_questions))
        extra_qs = (
            Question.objects
            .filter(status=QuestionStatus.ACTIVE, options__isnull=False)
            .exclude(pk__in=used_questions)
            .distinct()
            .order_by("?")[:min(shortfall, room_for_questions)]
        )
        for q in extra_qs:
            filler_items.append(DrillItem(source="filler", question=q))
            used_questions.add(q.pk)
        shortfall = size - (len(due_items) + len(wrong_items) + len(new_items) + len(filler_items))

    # วันแรกๆ ยังไม่มีอะไรให้ทบทวนเลย → เติมคำใหม่เพิ่มได้ แต่ห้ามเกินโควตาของวัน
    #
    # โควตาคำใหม่คือ *ขีดจำกัดการเรียนรู้* ไม่ใช่ตัวเลขที่ตั้งไว้เล่นๆ
    # ดันเกินเพื่อให้ชุดครบ 40 = สร้างหนี้การ์ดที่จะกลับมาถล่มในอีกสามวัน
    # ชุดที่สั้นกว่าเป้าในสัปดาห์แรกจึงถูกต้องแล้ว ขอแค่บอกให้ผู้ใช้รู้ตรงๆ
    if shortfall > 0 and len(new_items) < quota:
        room = min(shortfall, quota - len(new_items))
        for card in srs.new_queryset(learner):
            if room <= 0:
                break
            if card.pk in used_cards or card.vocab_id in used_new_vocabs:
                continue
            new_items.append(DrillItem(source="new", card=card))
            used_cards.add(card.pk)
            used_new_vocabs.add(card.vocab_id)
            room -= 1

    # ยังขาดอยู่หลังเติมทุกทาง → เติมด้วยการ์ดที่ยังไม่เคยเรียน (ในโควตา) หรือการ์ดที่เหลือ
    # ตั้งใจให้ที่ว่างตกเป็นของคำศัพท์เสมอ ไม่ใช่ดันข้อสอบจริงเกินเพดาน
    shortfall = size - (len(due_items) + len(wrong_items) + len(new_items) + len(filler_items))
    if shortfall > 0:
        spare = (
            Card.objects
            # ต้องเคยเรียนมาก่อน — ช่องนี้ชื่อ "ทวนเสริม" ไม่ใช่ช่องสอนคำใหม่
            # ถ้าปล่อยการ์ด reps=0 เข้ามา จะกลายเป็นการดันคำใหม่เกินโควตาของวัน
            # ซึ่งขัดกับตัวคุมโหลดที่เขียนไว้เองอีก 20 บรรทัดก่อนหน้า
            .filter(learner=learner, reps__gte=1)
            .exclude(pk__in=used_cards)
            .select_related("vocab")
            .order_by("due_at", "pk")[:shortfall]
        )
        for card in spare:
            filler_items.append(DrillItem(source="filler", card=card))
            used_cards.add(card.pk)

    items = _cluster_groups(_interleave([due_items, wrong_items, new_items, filler_items], rng))

    return DrillPlan(
        items=items,
        mix={
            "due": len(due_items),
            "wrong": len(wrong_items),
            "new": len(new_items),
            "filler": len(filler_items),
            "questions": len(used_questions),
            "max_questions": max_questions,
            "requested": size,
            "actual": len(items),
            "short_by": max(0, size - len(items)),
            "difficulty": _weekly_difficulty(learner, now.date()),
            "new_quota": quota,
            "in_freeze": srs.in_freeze(learner, now.date()),
        },
    )


def today_summary(learner: LearnerProfile, now: datetime | None = None) -> dict:
    """ตัวเลขสำหรับหน้า 'วันนี้' — เรียกก่อนผู้เรียนกดเริ่ม"""
    now = now or timezone.now()
    return {
        "due": srs.due_queryset(learner, now).count(),
        "wrong_open": ErrorLog.objects.filter(learner=learner, resolved_at__isnull=True).count(),
        "new_quota": srs.new_quota_today(learner, now),
        "new_available": srs.new_queryset(learner).count(),
        "drill_size": learner.drill_size or settings.DRILL_DEFAULT_SIZE,
        "days_to_exam": srs.days_to_exam(learner, now.date()),
        "in_freeze": srs.in_freeze(learner, now.date()),
        "difficulty": _weekly_difficulty(learner, now.date()),
        "has_baseline": learner.has_baseline,
    }
