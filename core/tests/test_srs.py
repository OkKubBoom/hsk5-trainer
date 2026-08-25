"""ทดสอบตัวจัดตารางทบทวน

scheduler ที่ผิดจะผิดแบบเงียบ — ผู้เรียนจะไม่มีทางรู้ว่าคำที่ควรกลับมาถาม
วันนี้ถูกเลื่อนไปหลังวันสอบ จนกระทั่งสอบตกไปแล้ว
"""
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from core import srs
from core.models import Card, CardState, CardType, LearnerProfile, Rating, User, VocabItem


class SchedulerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("nong", password="x")
        self.learner = LearnerProfile.objects.create(
            user=self.user,
            target_exam_date=timezone.localdate() + timedelta(days=100),
            new_words_per_day=14,
        )
        self.vocab = VocabItem.objects.create(
            hanzi="随着", pinyin="suízhe", meaning_th="พร้อมกับ", frequency_rank=1,
        )
        self.card = Card.objects.create(
            learner=self.learner, vocab=self.vocab, card_type=CardType.RECOGNIZE,
        )

    def test_first_good_review_schedules_one_day(self):
        srs.review(self.card, Rating.GOOD)
        self.card.refresh_from_db()
        self.assertEqual(self.card.interval_days, 1.0)
        self.assertEqual(self.card.state, CardState.REVIEW)
        self.assertIsNotNone(self.card.due_at)

    def test_intervals_grow_then_plateau(self):
        seen = []
        for _ in range(6):
            srs.review(self.card, Rating.GOOD)
            self.card.refresh_from_db()
            seen.append(self.card.interval_days)
        self.assertEqual(seen[0], 1.0)
        self.assertEqual(seen[1], 3.0)
        self.assertGreater(seen[2], seen[1])
        # ต้องไม่มีค่าไหนเกินเพดานวันสอบ
        cap = srs.days_to_exam(self.learner) * srs.DEADLINE_RATIO
        self.assertTrue(all(v <= cap + 0.001 for v in seen), seen)

    def test_again_resets_and_counts_lapse(self):
        srs.review(self.card, Rating.GOOD)
        srs.review(self.card, Rating.GOOD)
        srs.review(self.card, Rating.AGAIN)
        self.card.refresh_from_db()
        self.assertEqual(self.card.interval_days, 0.0)
        self.assertEqual(self.card.lapses, 1)
        self.assertEqual(self.card.state, CardState.LAPSED)
        # นัดกลับมาใน 10 นาที ไม่ใช่พรุ่งนี้
        self.assertLess((self.card.due_at - timezone.now()).total_seconds(), 700)

    def test_ease_stays_inside_bounds(self):
        for _ in range(30):
            srs.review(self.card, Rating.AGAIN)
        self.card.refresh_from_db()
        self.assertGreaterEqual(self.card.ease, srs.MIN_EASE)

        card2 = Card.objects.create(
            learner=self.learner, vocab=self.vocab, card_type=CardType.AUDIO,
        )
        for _ in range(30):
            srs.review(card2, Rating.EASY)
        card2.refresh_from_db()
        self.assertLessEqual(card2.ease, srs.MAX_EASE)

    def test_interval_never_scheduled_past_exam(self):
        """นี่คือเหตุผลที่ไม่ใช้ SM-2 ตรงๆ"""
        self.learner.target_exam_date = timezone.localdate() + timedelta(days=10)
        self.learner.save()
        for _ in range(10):
            srs.review(self.card, Rating.EASY)
            self.card.refresh_from_db()
            self.assertLessEqual(self.card.interval_days, 10 * srs.DEADLINE_RATIO + 0.001)

    def test_cap_interval_after_exam_date(self):
        self.learner.target_exam_date = timezone.localdate() - timedelta(days=3)
        self.learner.save()
        self.assertEqual(srs.cap_interval(90, self.learner), 1.0)

    def test_review_log_written_every_time(self):
        srs.review(self.card, Rating.GOOD, elapsed_ms=4200)
        log = self.card.reviews.first()
        self.assertEqual(log.rating, Rating.GOOD)
        self.assertEqual(log.elapsed_ms, 4200)
        self.assertEqual(log.scheduler_version, srs.SCHEDULER_VERSION)


class QuotaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("nong2", password="x")
        self.learner = LearnerProfile.objects.create(
            user=self.user,
            target_exam_date=timezone.localdate() + timedelta(days=100),
            new_words_per_day=18,
        )

    def _make_due_cards(self, n):
        past = timezone.now() - timedelta(days=1)
        for i in range(n):
            v = VocabItem.objects.create(
                hanzi=f"字{i}", pinyin="zi", meaning_th="x", frequency_rank=i + 1,
            )
            Card.objects.create(
                learner=self.learner, vocab=v, card_type=CardType.RECOGNIZE,
                state=CardState.REVIEW, due_at=past, interval_days=2,
            )

    def test_full_quota_when_backlog_is_small(self):
        self._make_due_cards(5)
        self.assertEqual(srs.new_quota_today(self.learner), 18)

    def test_quota_halved_when_backlog_climbs(self):
        self._make_due_cards(100)   # 70% ของเพดาน 130
        self.assertEqual(srs.new_quota_today(self.learner), 9)

    def test_quota_zero_when_backlog_hits_ceiling(self):
        """ตัวคุมโหลด — กฎที่กันไม่ให้ผู้เรียนเลิกกลางคัน"""
        self._make_due_cards(135)
        self.assertEqual(srs.new_quota_today(self.learner), 0)

    def test_quota_zero_during_freeze(self):
        self.learner.target_exam_date = timezone.localdate() + timedelta(days=7)
        self.learner.save()
        self.assertTrue(srs.in_freeze(self.learner))
        self.assertEqual(srs.new_quota_today(self.learner), 0)
