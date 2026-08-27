"""เทสต์โหมดฝึกจำคำศัพท์ — จุดที่ผิดแล้วเงียบ

สองเรื่องที่ผิดแล้วไม่มีใครรู้จนสาย:
  1. ถ้าโหมดนี้ไปเลื่อนตารางทบทวนของ SRS ระยะห่างจะพองจนคำหลุดหายไปเงียบๆ
  2. ถ้าขั้น 'ดูคำ' ย้อนกลับได้หลังกดเริ่มทดสอบ ตัวเลขความแม่นจะไม่ได้วัดอะไรเลย
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import review
from core.accounts import create_learner
from core.models import (
    Card, CardState, ErrorLog, Rating, ReviewMode, ReviewPhase, ReviewSession,
    ReviewLog, VocabItem,
)


class ReviewBaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for i in range(30):
            VocabItem.objects.create(
                hanzi=f"字{i}", pinyin=f"zi{i}", meaning_th=f"ความหมาย {i}",
                example_zh=f"这是字{i}。", hsk_level=5,
            )
        cls.learner, _ = create_learner(
            username="kid", password="passpass1",
            exam_date=timezone.localdate() + timedelta(days=60),
        )

    def learn(self, n, **kw):
        """ทำให้การ์ด n ใบกลายเป็น 'เคยเรียนแล้ว' ตามค่าที่กำหนด"""
        cards = list(Card.objects.filter(learner=self.learner)[:n])
        for c in cards:
            for field, value in {"reps": 3, "interval_days": 5.0, **kw}.items():
                setattr(c, field, value)
            c.state = kw.get("state", CardState.REVIEW)
            c.save()
        return cards


class PoolTests(ReviewBaseTests):
    def test_ยังไม่เคยเรียนไม่ถูกหยิบมาทบทวน(self):
        """โหมดนี้คือการทบทวน ไม่ใช่การเรียนคำใหม่ — คำใหม่มีที่ในชุดฝึกรายวันแล้ว"""
        self.assertEqual(review.build_pool(self.learner).count(), 0)
        self.learn(4)
        self.assertEqual(review.build_pool(self.learner).count(), 4)

    def test_ระดับความแม่นไม่ทับกัน(self):
        """คำหนึ่งคำต้องอยู่ระดับเดียว มิฉะนั้นผลรวมจะเกินจำนวนคำจริง"""
        self.learn(3, interval_days=1.0, reps=1)
        self.learn(2, interval_days=20.0)
        counts = {t["key"]: t["count"] for t in review.tier_counts(self.learner)}
        by_tier = sum(v for k, v in counts.items() if k)
        self.assertEqual(by_tier, counts[""])

    def test_เคยลืมมาก่อนถูกจัดเข้ากองลืมไม่ใช่กองตามระยะห่าง(self):
        cards = self.learn(2, interval_days=30.0)
        cards[0].lapses = 2
        cards[0].save()
        counts = {t["key"]: t["count"] for t in review.tier_counts(self.learner)}
        self.assertEqual(counts["lapsed"], 1)
        self.assertEqual(counts["solid"], 1)

    def test_ช่วงเวลานับเฉพาะคำที่ตอบถูก(self):
        """ตอบผิดเมื่อวานไม่ใช่ 'คำที่จำได้เมื่อวาน' — คนละกองกัน"""
        cards = self.learn(2)
        yesterday = timezone.now() - timedelta(days=1)
        for card, rating in ((cards[0], Rating.GOOD), (cards[1], Rating.AGAIN)):
            log = ReviewLog.objects.create(card=card, rating=rating)
            ReviewLog.objects.filter(pk=log.pk).update(reviewed_at=yesterday)

        pool = review.build_pool(self.learner, window=1)
        self.assertEqual([c.pk for c in pool], [cards[0].pk])


class FlowTests(ReviewBaseTests):
    def setUp(self):
        self.client.login(username="kid", password="passpass1")

    def test_เริ่มรอบใหม่ต้องอยู่ขั้นดูคำก่อนเสมอ(self):
        self.learn(5)
        session = review.start(self.learner, size=10)
        self.assertEqual(session.phase, ReviewPhase.STUDY)
        self.assertTrue(session.in_study)

    def test_ยังไม่กดพร้อมเข้าหน้าทดสอบไม่ได้(self):
        """กันไม่ให้ข้ามขั้นดูคำด้วยการพิมพ์ URL ตรงๆ"""
        self.learn(5)
        session = review.start(self.learner, size=5)
        res = self.client.get(reverse("review_run", args=[session.pk]))
        self.assertRedirects(res, reverse("review_study", args=[session.pk]))

    def test_กดเริ่มทดสอบแล้วย้อนกลับไปดูคำไม่ได้(self):
        """ถ้าย้อนได้ = เปิดดูเฉลยกลางคันได้ แล้วคะแนนไม่ได้วัดอะไร"""
        self.learn(5)
        session = review.start(self.learner, size=5)
        review.begin_test(session)
        res = self.client.get(reverse("review_study", args=[session.pk]))
        self.assertRedirects(res, reverse("review_run", args=[session.pk]))

    def test_ออกกลางคันแล้วกลับมาต่อข้อเดิม(self):
        self.learn(5)
        session = review.start(self.learner, size=5)
        review.begin_test(session)
        card = review.current_card(session)
        review.submit(session, card, given=card.vocab.meaning_th)
        review.advance(session)

        session.refresh_from_db()
        self.assertEqual(session.position, 1)
        self.assertEqual(review.current_card(session).pk, session.queue[1])

    def test_เริ่มรอบใหม่ปิดรอบเก่าที่ค้าง(self):
        """สองรอบเปิดพร้อมกันทำให้ปุ่ม 'ทำต่อ' ชี้ผิดรอบ"""
        self.learn(5)
        first = review.start(self.learner, size=5)
        second = review.start(self.learner, size=5)
        first.refresh_from_db()
        self.assertIsNotNone(first.finished_at)
        self.assertEqual(review.running(self.learner).pk, second.pk)

    def test_ไม่มีคำเข้าเงื่อนไขคืนค่าว่างไม่ใช่รอบเปล่า(self):
        self.assertIsNone(review.start(self.learner, size=10))
        self.assertEqual(ReviewSession.objects.count(), 0)


class SafetyTests(ReviewBaseTests):
    """กฎที่ทำให้โหมดนี้ทวนกี่รอบก็ได้โดยไม่ทำสถิติเพี้ยน"""

    def test_ตอบถูกต้องไม่เลื่อนตารางทบทวน(self):
        card = self.learn(1)[0]
        before = (card.interval_days, card.ease, card.reps, card.due_at)

        session = review.start(self.learner, size=1)
        review.begin_test(session)
        review.submit(session, card, given=card.vocab.meaning_th)

        card.refresh_from_db()
        self.assertEqual((card.interval_days, card.ease, card.reps, card.due_at), before)
        self.assertEqual(ReviewLog.objects.filter(card=card).count(), 0)

    def test_ตอบผิดก็ไม่เลื่อนตารางแต่ต้องเข้าคิวคำที่เคยผิด(self):
        """ตอบผิดคือสัญญาณจริง — ชุดฝึกวันถัดไปมีโควตา 30% รับช่วงต่ออยู่แล้ว"""
        card = self.learn(1)[0]
        before = card.interval_days

        session = review.start(self.learner, size=1)
        review.begin_test(session)
        outcome = review.submit(session, card, given="ตอบมั่ว")

        card.refresh_from_db()
        self.assertFalse(outcome["is_correct"])
        self.assertEqual(card.interval_days, before)
        self.assertTrue(
            ErrorLog.objects.filter(learner=self.learner, vocab=card.vocab,
                                    resolved_at__isnull=True).exists()
        )

    def test_ทดสอบแบบเลือกตัวอักษรตรวจด้วยตัวอักษรไม่ใช่ความหมาย(self):
        card = self.learn(1)[0]
        session = review.start(self.learner, size=1, mode=ReviewMode.HANZI)
        review.begin_test(session)
        outcome = review.submit(session, card, given=card.vocab.hanzi)
        self.assertTrue(outcome["is_correct"])

    def test_ตัวเลือกมีสี่ตัวและมีคำตอบที่ถูกอยู่ด้วยเสมอ(self):
        card = self.learn(1)[0]
        for mode in (ReviewMode.MEANING, ReviewMode.HANZI):
            q = review.make_question(card, mode, 1, 1)
            self.assertEqual(len(q.choices), 4, mode)
            self.assertIn(q.answer, q.choices, mode)
            self.assertEqual(len(set(q.choices)), 4, mode)

    def test_สถิติรายวันแยกจากสถิติหลัก(self):
        card = self.learn(1)[0]
        session = review.start(self.learner, size=1)
        review.begin_test(session)
        review.submit(session, card, given=card.vocab.meaning_th)

        stats = review.stats(self.learner)
        self.assertEqual(stats["today_answered"], 1)
        self.assertEqual(stats["today_accuracy"], 100)
