"""ทดสอบ Daily Drill Engine

ข้อที่สำคัญที่สุดคือ test_size_is_constant_over_time — กฎ +10% ทบต้น
ที่เสนอมาตอนแรกจะทำให้ชุดข้อสอบวันที่ 33 มี 211 ข้อ และวันสอบมี 324,940 ข้อ
เทสต์นี้มีไว้กันไม่ให้ใครเผลอเอากฎนั้นกลับเข้ามา
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core import selection, srs
from core.models import (
    Card, CardState, CardType, ErrorCode, ErrorLog, LearnerProfile,
    Question, QuestionStatus, QuestionType, Section, User, VocabItem,
)


class DrillBuilderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("nong", password="x")
        self.learner = LearnerProfile.objects.create(
            user=self.user,
            target_exam_date=timezone.localdate() + timedelta(days=100),
            new_words_per_day=18,
            drill_size=40,
        )
        self.vocabs = [
            VocabItem.objects.create(
                hanzi=f"词{i}", pinyin=f"ci{i}", meaning_th=f"ความหมาย {i}", frequency_rank=i + 1,
            )
            for i in range(200)
        ]

    def _card(self, vocab, *, due_days_ago=None, state=CardState.NEW):
        return Card.objects.create(
            learner=self.learner, vocab=vocab, card_type=CardType.RECOGNIZE,
            state=state,
            due_at=(timezone.now() - timedelta(days=due_days_ago)) if due_days_ago is not None else None,
            interval_days=2 if due_days_ago is not None else 0,
        )

    def test_plan_hits_requested_size_when_material_is_plentiful(self):
        for v in self.vocabs[:60]:
            self._card(v, due_days_ago=1, state=CardState.REVIEW)
        for v in self.vocabs[60:120]:
            self._card(v)
        plan = selection.build_daily_drill(self.learner, seed=1)
        self.assertEqual(plan.size, 40)

    def test_mix_follows_configured_ratio(self):
        # กลุ่มที่ถึงกำหนดทบทวน
        for v in self.vocabs[:40]:
            self._card(v, due_days_ago=1, state=CardState.REVIEW)
        # กลุ่มที่เคยผิด — มีการ์ดแต่ยังไม่ถึงกำหนด จึงไม่ทับกับกลุ่มบน
        for v in self.vocabs[40:60]:
            c = self._card(v, state=CardState.REVIEW)
            c.due_at = timezone.now() + timedelta(days=5)
            c.interval_days = 5
            c.save()
            ErrorLog.record(
                self.learner, ErrorCode.VOCAB, v.hanzi, section=Section.VOCAB, vocab=v,
            )
        # กลุ่มคำใหม่
        for v in self.vocabs[100:160]:
            self._card(v)

        plan = selection.build_daily_drill(self.learner, seed=7)
        self.assertEqual(plan.mix["due"], 20)     # 50% ของ 40
        self.assertEqual(plan.mix["wrong"], 12)   # 30%
        self.assertEqual(plan.mix["new"], 8)      # 20%
        self.assertEqual(plan.size, 40)

    def test_wrong_bucket_never_duplicates_a_due_card(self):
        """ถ้าคำที่เคยผิดถูกหยิบไปเป็นข้อทบทวนแล้ว ห้ามนับซ้ำในโควตา 'เคยผิด'

        ชุดจะถูกเติมให้ครบด้วย filler แทน — ขนาดคงที่คือสัญญาที่ให้ผู้เรียนไว้
        """
        for v in self.vocabs[:60]:
            self._card(v, due_days_ago=1, state=CardState.REVIEW)
        for v in self.vocabs[:20]:
            ErrorLog.record(
                self.learner, ErrorCode.VOCAB, v.hanzi, section=Section.VOCAB, vocab=v,
            )
        plan = selection.build_daily_drill(self.learner, seed=7)
        keys = [i.key for i in plan.items]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(plan.size, 40)

    def test_size_is_constant_over_time(self):
        """ขนาดชุดต้องไม่โตตามวัน — นี่คือกฎกลางของทั้งระบบ"""
        for v in self.vocabs[:150]:
            self._card(v, due_days_ago=1, state=CardState.REVIEW)
        base = timezone.now()
        sizes = {
            selection.build_daily_drill(self.learner, now=base + timedelta(days=d), seed=3).size
            for d in (0, 7, 21, 33, 60)
        }
        self.assertEqual(sizes, {40})

    def test_errors_seen_more_often_come_first(self):
        for v in self.vocabs[:40]:
            self._card(v, due_days_ago=1, state=CardState.REVIEW)
        hot, cold = self.vocabs[100], self.vocabs[101]
        self._card(hot, due_days_ago=None, state=CardState.REVIEW)
        self._card(cold, due_days_ago=None, state=CardState.REVIEW)
        for _ in range(9):
            ErrorLog.record(self.learner, ErrorCode.VOCAB, hot.hanzi,
                            section=Section.VOCAB, vocab=hot)
        ErrorLog.record(self.learner, ErrorCode.VOCAB, cold.hanzi,
                        section=Section.VOCAB, vocab=cold)
        plan = selection.build_daily_drill(self.learner, seed=5)
        wrong_hanzi = [i.card.vocab.hanzi for i in plan.items
                       if i.source == "wrong" and i.card]
        self.assertIn(hot.hanzi, wrong_hanzi)

    def test_no_new_cards_during_freeze(self):
        self.learner.target_exam_date = timezone.localdate() + timedelta(days=5)
        self.learner.save()
        for v in self.vocabs[:60]:
            self._card(v, due_days_ago=1, state=CardState.REVIEW)
        for v in self.vocabs[60:120]:
            self._card(v)
        plan = selection.build_daily_drill(self.learner, seed=2)
        self.assertEqual(plan.mix["new"], 0)
        self.assertTrue(plan.mix["in_freeze"])

    def test_backlog_ceiling_stops_new_cards(self):
        for v in self.vocabs[:140]:
            self._card(v, due_days_ago=1, state=CardState.REVIEW)
        for v in self.vocabs[140:180]:
            self._card(v)
        plan = selection.build_daily_drill(self.learner, seed=4)
        self.assertEqual(plan.mix["new"], 0)
        self.assertEqual(plan.mix["new_quota"], 0)

    def test_no_duplicate_items_in_one_plan(self):
        for v in self.vocabs[:80]:
            self._card(v, due_days_ago=1, state=CardState.REVIEW)
        for v in self.vocabs[:30]:
            ErrorLog.record(self.learner, ErrorCode.VOCAB, v.hanzi,
                            section=Section.VOCAB, vocab=v)
        plan = selection.build_daily_drill(self.learner, seed=11)
        keys = [i.key for i in plan.items]
        self.assertEqual(len(keys), len(set(keys)))

    def test_sources_are_interleaved_not_blocked(self):
        """คละชนิดข้อในเซสชันเดียวจำได้นานกว่าทำทีละกอง"""
        for v in self.vocabs[:60]:
            self._card(v, due_days_ago=1, state=CardState.REVIEW)
        for v in self.vocabs[60:120]:
            self._card(v)
        plan = selection.build_daily_drill(self.learner, seed=13)
        sources = [i.source for i in plan.items]
        switches = sum(1 for a, b in zip(sources, sources[1:]) if a != b)
        self.assertGreater(switches, 5, sources)

    def test_new_word_appears_once_per_session(self):
        """หนึ่งคำมีสองการ์ด (อ่านได้ / ฟังออก) แต่คำใหม่ต้องโผล่ครั้งเดียวต่อเซสชัน"""
        for v in self.vocabs[:30]:
            Card.objects.create(learner=self.learner, vocab=v, card_type=CardType.RECOGNIZE)
            Card.objects.create(learner=self.learner, vocab=v, card_type=CardType.AUDIO)
        plan = selection.build_daily_drill(self.learner, seed=21)
        new_vocab_ids = [i.card.vocab_id for i in plan.items if i.source == "new"]
        self.assertEqual(len(new_vocab_ids), len(set(new_vocab_ids)))

    def test_first_week_session_may_be_short_but_never_exceeds_quota(self):
        """วันแรกยังไม่มีอะไรให้ทบทวน — ชุดสั้นกว่าเป้าถูกต้องแล้ว
        แต่ห้ามดันคำใหม่เกินโควตาเพื่อให้ครบ 40"""
        self.learner.new_words_per_day = 14
        self.learner.save()
        for v in self.vocabs[:100]:
            Card.objects.create(learner=self.learner, vocab=v, card_type=CardType.RECOGNIZE)
        plan = selection.build_daily_drill(self.learner, seed=23)
        self.assertLessEqual(plan.mix["new"], 14)
        self.assertEqual(plan.mix["actual"], plan.size)
        self.assertEqual(plan.mix["short_by"], max(0, 40 - plan.size))

    def test_difficulty_ramps_as_exam_approaches(self):
        far = selection._weekly_difficulty(self.learner, timezone.localdate())
        self.assertEqual(far, "short")
        self.learner.target_exam_date = timezone.localdate() + timedelta(days=60)
        self.assertEqual(selection._weekly_difficulty(self.learner, timezone.localdate()), "exam")
        self.learner.target_exam_date = timezone.localdate() + timedelta(days=20)
        self.assertEqual(selection._weekly_difficulty(self.learner, timezone.localdate()), "exam_tight")

    def test_suspended_questions_never_selected(self):
        """ข้อที่ถูกรายงานว่าเฉลยผิดต้องไม่โผล่มาอีก"""
        q = Question.objects.create(
            qtype=QuestionType.SYNONYM_CLOZE, section=Section.READING,
            prompt_zh="这次事故____了很大的损失。", answer_text="造成",
            status=QuestionStatus.ACTIVE,
        )
        q.flag_wrong_answer()
        q.refresh_from_db()
        self.assertEqual(q.status, QuestionStatus.SUSPENDED)
        plan = selection.build_daily_drill(self.learner, seed=17)
        self.assertNotIn(q.pk, [i.question.pk for i in plan.items if i.question])


class TodaySummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("nong3", password="x")
        self.learner = LearnerProfile.objects.create(
            user=self.user, target_exam_date=timezone.localdate() + timedelta(days=90),
        )

    def test_summary_reports_missing_baseline(self):
        s = selection.today_summary(self.learner)
        self.assertFalse(s["has_baseline"])
        self.assertEqual(s["days_to_exam"], 90)
        self.assertFalse(s["in_freeze"])
