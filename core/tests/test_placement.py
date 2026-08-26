"""เทสต์ตรรกะแบบวัดระดับ — ผิดแล้วเงียบเหมือน SRS

ถ้าแปลผลพลาด ผู้เรียนจะได้โควตาคำใหม่ผิดไปทั้งเทอมโดยไม่มีอะไรเตือน
"""
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from core import placement
from core.models import LearnerProfile, PlacementTest, Role, User, VocabItem


class PlacementTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        for level, n in ((1, 8), (2, 8), (3, 10), (4, 20), (5, 30)):
            for i in range(n):
                VocabItem.objects.create(
                    hanzi=f"L{level}字{i}", pinyin=f"zi{i}",
                    meaning_th=f"ความหมายระดับ{level}-{i}",
                    hsk_level=level, frequency_rank=level * 100 + i,
                )
        user = User.objects.create_user("nong", password="x", role=Role.LEARNER)
        cls.learner = LearnerProfile.objects.create(
            user=user, target_exam_date=timezone.localdate() + timedelta(days=100),
        )

    def test_pick_words_covers_every_level(self):
        words = placement.pick_words(40, seed=7)
        levels = {w.hsk_level for w in words}
        self.assertEqual(len(words), 40)
        self.assertTrue({4, 5}.issubset(levels), "ต้องมีคำระดับ 4 และ 5 เสมอ")

    def test_question_has_four_unique_choices_including_answer(self):
        vocab = VocabItem.objects.filter(hsk_level=5).first()
        q = placement.make_question(vocab)
        self.assertEqual(len(q.choices), 4)
        self.assertEqual(len(set(q.choices)), 4, "ตัวเลือกห้ามซ้ำกัน")
        self.assertIn(vocab.meaning_th, q.choices)

    def test_unknown_is_not_counted_as_wrong_answer(self):
        test = placement.start(self.learner, size=4, seed=1)
        vocab = placement.next_vocab(test)
        placement.record(test, vocab, given="", said_unknown=True)
        answer = test.answers.get()
        self.assertTrue(answer.said_unknown)
        self.assertFalse(answer.is_correct)
        self.assertEqual(placement.score(test)["unknown_pressed"], 1)

    def test_queue_is_stable_across_refresh(self):
        test = placement.start(self.learner, size=5, seed=3)
        first = placement.next_vocab(test)
        self.assertEqual(placement.next_vocab(test).pk, first.pk, "ยังไม่ตอบ ต้องได้คำเดิม")
        placement.record(test, first, given=first.meaning_th)
        self.assertNotEqual(placement.next_vocab(test).pk, first.pk, "ตอบแล้วต้องข้ามไปคำถัดไป")

    def test_all_correct_gives_high_estimate_and_level_five_start(self):
        test = placement.start(self.learner, size=30, seed=5)
        while (vocab := placement.next_vocab(test)) is not None:
            placement.record(test, vocab, given=vocab.meaning_th)
        result = placement.finish(test)
        self.assertGreater(result["known_vocab_estimate"], 1500)
        self.assertEqual(result["start_level"], 5)

    def test_all_wrong_starts_from_lowest_level(self):
        test = placement.start(self.learner, size=30, seed=5)
        while (vocab := placement.next_vocab(test)) is not None:
            placement.record(test, vocab, given="ผิดแน่นอน")
        result = placement.finish(test)
        self.assertLess(result["known_vocab_estimate"], 200)
        self.assertEqual(result["start_level"], min(int(k) for k in result["by_level"]))

    def test_finish_writes_settings_back_to_profile(self):
        test = placement.start(self.learner, size=20, seed=9)
        while (vocab := placement.next_vocab(test)) is not None:
            placement.record(test, vocab, given=vocab.meaning_th)
        result = placement.finish(test)
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.known_vocab_estimate, result["known_vocab_estimate"])
        self.assertEqual(self.learner.new_words_per_day, result["suggested_new_words_per_day"])

    def test_new_words_per_day_never_absurd(self):
        """เหลือเวลาน้อยมาก โควตาต้องไม่พุ่งเป็นร้อยคำต่อวันจนทำจริงไม่ได้"""
        self.learner.target_exam_date = timezone.localdate() + timedelta(days=3)
        self.learner.save()
        test = placement.start(self.learner, size=10, seed=2)
        while (vocab := placement.next_vocab(test)) is not None:
            placement.record(test, vocab, given="ผิด")
        result = placement.finish(test)
        self.assertLessEqual(result["suggested_new_words_per_day"], 30)
        self.assertGreaterEqual(result["suggested_new_words_per_day"], 5)
