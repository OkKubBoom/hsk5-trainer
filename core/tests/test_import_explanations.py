"""ทดสอบคำสั่งเติมคำอธิบายเฉลย

จุดที่ผิดแล้วเงียบ: ถ้าคำอธิบายไปติดผิดข้อ ผู้เรียนจะอ่านเหตุผลของข้ออื่น
ตอนที่เพิ่งตอบผิด ซึ่งแย่กว่าไม่มีคำอธิบายเลย จึงต้องคุมสองเรื่อง —
ห้ามใส่เมื่อเงื่อนไขตรงหลายข้อ และห้ามทับของเดิมโดยไม่ได้สั่ง
"""
import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import Question, Section


def _q(**kw):
    base = dict(qtype="reading_mc", section=Section.READING,
                prompt_zh="…", answer_text="ถูก")
    return Question.objects.create(**{**base, **kw})


def _write(tmp_path, items):
    path = tmp_path / "data"
    path.mkdir(exist_ok=True)
    (path / "explanations_extra.json").write_text(
        json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


class ImportExplanationsTests(TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = Path(tempfile.mkdtemp())

    def _run(self, items, *args):
        _write(self.tmp, items)
        out = StringIO()
        with override_settings(BASE_DIR=self.tmp):
            call_command("import_explanations", *args, stdout=out)
        return out.getvalue()

    def test_writes_to_the_matching_question(self):
        q = _q(source_ref="H51002 ข้อ 70")
        self._run([{"match": {"source_ref": "H51002 ข้อ 70"},
                    "explanation": {"why_correct": "เพราะอย่างนี้"}}], "--apply")
        q.refresh_from_db()
        self.assertEqual(q.explanation["why_correct"], "เพราะอย่างนี้")

    def test_dry_run_writes_nothing(self):
        q = _q(source_ref="H51002 ข้อ 70")
        out = self._run([{"match": {"source_ref": "H51002 ข้อ 70"},
                          "explanation": {"why_correct": "x"}}])
        q.refresh_from_db()
        self.assertFalse(q.explanation)
        self.assertIn("--apply", out)

    def test_skips_when_the_match_hits_more_than_one_question(self):
        # ใส่ผิดข้อแย่กว่าไม่ใส่ — เงื่อนไขกำกวมต้องข้าม ไม่ใช่เดา
        a = _q(source_ref="ซ้ำ")
        b = _q(source_ref="ซ้ำ")
        out = self._run([{"match": {"source_ref": "ซ้ำ"},
                          "explanation": {"why_correct": "x"}}], "--apply")
        a.refresh_from_db(); b.refresh_from_db()
        self.assertFalse(a.explanation)
        self.assertFalse(b.explanation)
        self.assertIn("กำกวม 1", out)

    def test_does_not_overwrite_an_existing_explanation(self):
        q = _q(source_ref="H51002 ข้อ 70", explanation={"why_correct": "ครูเขียนไว้"})
        self._run([{"match": {"source_ref": "H51002 ข้อ 70"},
                    "explanation": {"why_correct": "ของใหม่"}}], "--apply")
        q.refresh_from_db()
        self.assertEqual(q.explanation["why_correct"], "ครูเขียนไว้")

    def test_force_overwrites(self):
        q = _q(source_ref="H51002 ข้อ 70", explanation={"why_correct": "เก่า"})
        self._run([{"match": {"source_ref": "H51002 ข้อ 70"},
                    "explanation": {"why_correct": "ใหม่"}}], "--apply", "--force")
        q.refresh_from_db()
        self.assertEqual(q.explanation["why_correct"], "ใหม่")

    def test_reports_a_match_that_finds_nothing(self):
        out = self._run([{"match": {"source_ref": "ไม่มีข้อนี้"},
                          "explanation": {"why_correct": "x"}}], "--apply")
        self.assertIn("ไม่เจอ 1", out)


class ShippedFileTests(TestCase):
    """ไฟล์จริงที่ commit ไว้ต้องใช้ได้ ไม่ใช่แค่ไฟล์ทดสอบ"""

    def test_every_entry_has_what_the_page_needs(self):
        from django.conf import settings
        from pathlib import Path
        data = json.loads(
            (Path(settings.BASE_DIR) / "data" / "explanations_extra.json")
            .read_text(encoding="utf-8"))
        items = data["items"]
        self.assertEqual(len(items), 9)
        for item in items:
            ex = item["explanation"]
            self.assertTrue(item["match"], item)
            for key in ("why_correct", "hint", "key_vocab", "error_code", "source"):
                self.assertIn(key, ex, item["match"])
            # ป้าย AI ต้องติดไว้เสมอ ไม่งั้นผู้เรียนเข้าใจว่าครูตรวจแล้ว
            self.assertEqual(ex["source"], "ai_generated")
            self.assertTrue(all(v.get("hanzi") and v.get("note") for v in ex["key_vocab"]))
