"""กวาดเทมเพลตหาความผิดพลาดที่โผล่บนหน้าจอผู้ใช้โดยไม่มีใครสังเกต

เขียนขึ้นเพราะเผลอเขียน {# … #} คร่อมสองบรรทัด ซึ่ง Django **ไม่รองรับ**
คอมเมนต์นั้นเลยถูกพิมพ์ออกมาเป็นข้อความในหน้าคลังคำศัพท์และการ์ดเฉลย
ไม่มีเทสต์ไหนจับได้เพราะหน้ายังขึ้น 200 ปกติ — พังแบบเงียบสนิท
"""
import pathlib

from django.conf import settings
from django.test import TestCase

TEMPLATES = sorted(pathlib.Path(settings.BASE_DIR, "templates").rglob("*.html"))


class CommentSyntaxTests(TestCase):
    def test_no_single_line_comment_spans_two_lines(self):
        """{# … #} ต้องปิดในบรรทัดเดียว หลายบรรทัดต้องใช้ {% comment %}"""
        bad = []
        for path in TEMPLATES:
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "{#" in line and "#}" not in line.split("{#", 1)[1]:
                    rel = path.relative_to(settings.BASE_DIR)
                    bad.append(f"{rel}:{lineno}")
        self.assertEqual(bad, [], "คอมเมนต์เหล่านี้จะถูกพิมพ์ให้ผู้ใช้เห็น: " + ", ".join(bad))

    def test_every_comment_block_is_closed(self):
        bad = []
        for path in TEMPLATES:
            src = path.read_text(encoding="utf-8")
            if src.count("{% comment %}") != src.count("{% endcomment %}"):
                bad.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertEqual(bad, [])

    def test_templates_that_use_a_filter_library_load_it(self):
        """ใช้ฟิลเตอร์ของเราโดยลืม {% load hsk %} = TemplateSyntaxError ตอนเปิดหน้า"""
        filters = ["pos_short", "pos_title", "paper_dots", "trap_ratio", "rank_class"]
        bad = []
        for path in TEMPLATES:
            src = path.read_text(encoding="utf-8")
            uses = any(f"|{f}" in src for f in filters)
            if uses and "{% load hsk %}" not in src:
                bad.append(str(path.relative_to(settings.BASE_DIR)))
        self.assertEqual(bad, [], "ลืม {% load hsk %}: " + ", ".join(bad))
