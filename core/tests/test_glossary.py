"""ทดสอบคำนอกคลัง — สำนวน/คำ HSK6+ ที่โผล่ในข้อสอบจริง

เหตุที่ต้องมี: คำแปลของคำพวกนี้อยู่ในระบบมาตลอด แต่เห็นได้เฉพาะหลังตอบข้อนั้น
ผู้เรียนที่ค้นหาจึงไม่เจอ แล้วออกไปเปิดแอปอื่นถามแทน (เจอจริงกับ 旗鼓相当)
"""
from django.test import TestCase

from core import glossary
from core.models import Question, Section, User, VocabItem


def _q(source_ref, key_vocab):
    return Question.objects.create(
        qtype="reading_mc", section=Section.READING, source_ref=source_ref,
        prompt_zh="…", answer_text="ถูก",
        explanation={"key_vocab": key_vocab},
    )


class GlossaryTests(TestCase):
    def setUp(self):
        _q("H51327 ข้อ 75", [{"hanzi": "旗鼓相当", "note": "สูสีกัน ก้ำกึ่งกัน"}])
        _q("H51001 ข้อ 71", [{"hanzi": "后者", "note": "อย่างหลัง"}])
        _q("H51002 ข้อ 72", [{"hanzi": "后者", "note": "อย่างหลัง (คู่กับ 前者)"}])
        _q("H51003 ข้อ 73", [{"hanzi": "影响", "note": "ส่งผล"}])
        VocabItem.objects.create(hanzi="影响", pinyin="yǐngxiǎng",
                                 meaning_th="ส่งผล", hsk_level=4)

    def test_out_of_library_words_are_listed(self):
        got = {r["hanzi"] for r in glossary.rows()}
        self.assertIn("旗鼓相当", got)
        self.assertIn("后者", got)

    def test_words_already_in_the_library_are_skipped(self):
        # ไม่งั้นจะซ้ำกับรายการหลักของหน้าคลังคำศัพท์
        self.assertNotIn("影响", {r["hanzi"] for r in glossary.rows()})

    def test_same_word_from_many_papers_is_one_row(self):
        row = next(r for r in glossary.rows() if r["hanzi"] == "后者")
        self.assertEqual(row["papers"], ["H51001", "H51002"])

    def test_shorter_note_contained_in_a_longer_one_is_dropped(self):
        row = next(r for r in glossary.rows() if r["hanzi"] == "后者")
        self.assertEqual(row["meaning_th"], "อย่างหลัง (คู่กับ 前者)")

    def test_search_matches_hanzi_pinyin_and_thai(self):
        self.assertEqual([r["hanzi"] for r in glossary.rows("旗鼓")], ["旗鼓相当"])
        self.assertEqual([r["hanzi"] for r in glossary.rows("สูสี")], ["旗鼓相当"])
        self.assertEqual([r["hanzi"] for r in glossary.rows("qígǔ")], ["旗鼓相当"])

    def test_entries_without_a_thai_note_are_skipped(self):
        _q("H51004 ข้อ 74", [{"hanzi": "无解"}])
        self.assertNotIn("无解", {r["hanzi"] for r in glossary.rows()})


class GlossaryPageTests(TestCase):
    def setUp(self):
        _q("H51327 ข้อ 75", [{"hanzi": "旗鼓相当", "note": "สูสีกัน ก้ำกึ่งกัน"}])
        self.user = User.objects.create_user("bam", password="x")
        self.client.force_login(self.user)

    def test_beyond_page_finds_the_word(self):
        res = self.client.get("/vocab/beyond/", {"q": "旗鼓相当"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "สูสีกัน ก้ำกึ่งกัน")
        self.assertContains(res, "H51327")

    def test_vocab_search_surfaces_out_of_library_hits(self):
        # ค้นที่หน้าคลังคำศัพท์แล้วไม่เจอในคลัง ต้องยังเห็นคำนอกคลัง
        res = self.client.get("/vocab/", {"q": "旗鼓相当"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["page"].paginator.count, 0)
        self.assertEqual([r["hanzi"] for r in res.context["beyond"]], ["旗鼓相当"])
        self.assertContains(res, "สูสีกัน ก้ำกึ่งกัน")

    def test_no_beyond_section_without_a_search(self):
        res = self.client.get("/vocab/")
        self.assertEqual(res.context["beyond"], [])
