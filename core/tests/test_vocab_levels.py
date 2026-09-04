"""ทดสอบการเลือกระดับคำศัพท์ที่จะเรียนใหม่

กฎที่ผิดแล้วเงียบ: การกรองต้องแตะเฉพาะ "คำใหม่" ห้ามแตะของที่ถึงกำหนดทบทวน
ถ้ากรองของที่ถึงกำหนดด้วย การ์ดของระดับที่ปิดไว้จะค้างอยู่ตลอดไป
นับเป็นของค้าง (ซึ่งกดโควตาคำใหม่ลง) แต่ไม่มีวันโผล่มาให้ทบทวนเลย
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core import srs
from core.models import Card, CardState, CardType, LearnerProfile, Rating, User, VocabItem


class VocabLevelFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("bam", password="x")
        self.learner = LearnerProfile.objects.create(
            user=self.user,
            target_exam_date=timezone.localdate() + timedelta(days=100),
        )
        self.cards = {}
        for i, level in enumerate([3, 4, 5]):
            vocab = VocabItem.objects.create(
                hanzi=f"字{level}", pinyin="zi", meaning_th="คำ",
                hsk_level=level, frequency_rank=i + 1,
            )
            self.cards[level] = Card.objects.create(
                learner=self.learner, vocab=vocab, card_type=CardType.RECOGNIZE,
            )

    def test_empty_means_every_level(self):
        self.assertEqual(srs.new_queryset(self.learner).count(), 3)

    def test_only_picked_levels_come_as_new(self):
        self.learner.vocab_levels = [5]
        self.learner.save(update_fields=["vocab_levels"])
        got = list(srs.new_queryset(self.learner))
        self.assertEqual([c.vocab.hsk_level for c in got], [5])

    def test_due_reviews_are_never_filtered(self):
        # การ์ด HSK3 เคยเรียนไปแล้วและถึงกำหนดทบทวน — ต้องมาแม้จะปิดระดับ 3 ไว้
        card = self.cards[3]
        srs.review(card, Rating.GOOD)
        card.refresh_from_db()
        card.due_at = timezone.now() - timedelta(days=1)
        card.save(update_fields=["due_at"])

        self.learner.vocab_levels = [5]
        self.learner.save(update_fields=["vocab_levels"])

        due = list(srs.due_queryset(self.learner))
        self.assertIn(card.pk, [c.pk for c in due])
        self.assertNotIn(card.pk, [c.pk for c in srs.new_queryset(self.learner)])


class ProfileLevelFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("chin", password="x")
        self.learner = LearnerProfile.objects.create(
            user=self.user,
            target_exam_date=timezone.localdate() + timedelta(days=100),
        )
        for i, level in enumerate([4, 5]):
            vocab = VocabItem.objects.create(
                hanzi=f"词{level}", pinyin="ci", meaning_th="คำ",
                hsk_level=level, frequency_rank=i + 1,
            )
            Card.objects.create(
                learner=self.learner, vocab=vocab, card_type=CardType.RECOGNIZE,
            )
        self.client.force_login(self.user)

    def test_post_saves_picked_levels(self):
        res = self.client.post("/profile/", {"form": "levels", "levels": ["5"]})
        self.assertEqual(res.status_code, 302)
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.vocab_levels, [5])

    def test_picking_every_level_stores_empty(self):
        # ติ๊กครบ = "ทุกระดับ" ไม่ใช่ล็อกไว้แค่ระดับที่มีอยู่วันนี้
        self.client.post("/profile/", {"form": "levels", "levels": ["4", "5"]})
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.vocab_levels, [])

    def test_unticking_everything_means_every_level(self):
        self.learner.vocab_levels = [5]
        self.learner.save(update_fields=["vocab_levels"])
        self.client.post("/profile/", {"form": "levels"})
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.vocab_levels, [])
        self.assertEqual(srs.new_queryset(self.learner).count(), 2)

    def test_page_shows_a_row_per_level(self):
        res = self.client.get("/profile/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual([r["level"] for r in res.context["levels"]], [4, 5])
        self.assertTrue(all(r["on"] for r in res.context["levels"]))
