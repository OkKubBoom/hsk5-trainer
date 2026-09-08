"""คำสั่งซ่อมประโยคตัวอย่าง ต้องบอกความจริงว่ายังพังอยู่ไหม

เดิมมันนับคำที่ "ซ่อมไปแล้ว" เป็นงานค้างทุกครั้งที่รัน — รันกี่รอบก็ขึ้น 24 คำ
ผลคือเจ้าของระบบตรวจไม่ได้เลยว่าเซิร์ฟเวอร์ซ่อมไปหรือยัง
เครื่องมือซ่อมที่บอกไม่ได้ว่าซ่อมเสร็จหรือยัง แย่กว่าไม่มีเครื่องมือ
"""
import json
from io import StringIO
from pathlib import Path
import tempfile

from django.core.management import call_command
from django.test import TestCase
from unittest import mock

from core.models import VocabItem

ZH_GOOD, TH_GOOD = "我们要逐步解决这些问题。", "พวกเราต้องแก้ปัญหาเหล่านี้ไปทีละขั้น"
TH_WRONG = "คำแปลของประโยคอื่นที่ค้างอยู่"


class FixVocabExamplesTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "seed.txt").write_text(
            f"逐步|zhúbù|ทีละขั้น|{ZH_GOOD}\n", encoding="utf-8")
        (self.tmp / "merged.json").write_text(json.dumps(
            {"words": [{"hanzi": "逐步", "example_zh": ZH_GOOD, "example_th": TH_GOOD}]},
            ensure_ascii=False), encoding="utf-8")

    def _run(self, *args):
        out = StringIO()
        with mock.patch("core.management.commands.fix_vocab_examples.SEED",
                        self.tmp / "seed.txt"), \
             mock.patch("core.management.commands.fix_vocab_examples.MERGED",
                        self.tmp / "merged.json"):
            call_command("fix_vocab_examples", *args, stdout=out)
        return out.getvalue()

    def _word(self, th):
        return VocabItem.objects.create(
            hanzi="逐步", pinyin="zhúbù", meaning_th="ทีละขั้น",
            hsk_level=5, example_zh=ZH_GOOD, example_th=th)

    def test_repairs_a_mismatched_pair(self):
        v = self._word(TH_WRONG)
        self._run("--apply")
        v.refresh_from_db()
        self.assertEqual(v.example_th, TH_GOOD)

    def test_says_nothing_to_do_when_the_pair_is_already_right(self):
        self._word(TH_GOOD)
        out = self._run()
        self.assertIn("ไม่มีอะไรต้องซ่อม", out)

    def test_running_twice_reports_no_work_the_second_time(self):
        # นี่คือบั๊กจริง — รันซ้ำแล้วยังขึ้น "ต้องซ่อม" ทำให้ตรวจสถานะไม่ได้
        self._word(TH_WRONG)
        first = self._run("--apply")
        second = self._run("--apply")
        self.assertIn("คืนคู่ที่ถูกต้อง 1 คำ", first)
        self.assertIn("ไม่มีอะไรต้องซ่อม", second)

    def test_dry_run_changes_nothing(self):
        v = self._word(TH_WRONG)
        self._run()
        v.refresh_from_db()
        self.assertEqual(v.example_th, TH_WRONG)

    def test_a_word_with_no_translation_is_left_alone(self):
        v = self._word("")
        out = self._run("--apply")
        v.refresh_from_db()
        self.assertEqual(v.example_th, "")
        self.assertIn("ไม่มีอะไรต้องซ่อม", out)
