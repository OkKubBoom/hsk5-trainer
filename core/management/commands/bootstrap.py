"""ตั้งค่าระบบครั้งแรกบนเซิร์ฟเวอร์ใหม่ — รันคำสั่งเดียวจบ

    python manage.py bootstrap

รันซ้ำได้ ไม่สร้างข้อมูลซ้ำ ใช้ตอน deploy ครั้งแรกหรือตอนย้ายเซิร์ฟเวอร์
ไม่สร้างบัญชีผู้ใช้ให้ — ต้องสร้างเองเพื่อจะได้ตั้งรหัสผ่านที่ไม่ซ้ำใคร
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.models import Question, SynonymGroup, VocabItem


class Command(BaseCommand):
    help = "โหลดคำศัพท์ ข้อสอบ และกลุ่มคำใกล้เคียงเข้าฐานข้อมูลใหม่"

    def add_arguments(self, parser):
        parser.add_argument("--skip-exams", action="store_true",
                            help="ข้ามการโหลดข้อสอบ (เช่นเซิร์ฟเวอร์สาธิตที่ไม่ควรมีข้อสอบลิขสิทธิ์)")

    def handle(self, *args, **opts):
        self.stdout.write("1/3 คำศัพท์…")
        call_command("import_vocab")

        if opts["skip_exams"]:
            self.stdout.write("2/3 ข้อสอบ — ข้ามตามที่สั่ง")
        elif Question.objects.filter(source_type="official_past_paper").exists():
            self.stdout.write("2/3 ข้อสอบ — มีอยู่แล้ว ข้าม")
        else:
            self.stdout.write("2/3 ข้อสอบ…")
            call_command("loaddata", "data/exam_fixture.json")

        self.stdout.write("3/3 กลุ่มคำใกล้เคียง…")
        try:
            call_command("import_synonyms")
        except Exception:
            # ต้องใช้ data/exam_corpus/ ซึ่งไม่ได้อยู่ในรีโป — ไม่ใช่เรื่องผิดปกติ
            self.stdout.write("   ข้าม (ไม่มีไฟล์ต้นทางบนเครื่องนี้)")

        self.stdout.write(self.style.SUCCESS(
            f"\nพร้อมใช้งาน — คำศัพท์ {VocabItem.objects.count()} คำ · "
            f"ข้อสอบ {Question.objects.count()} ข้อ · กลุ่มคำ {SynonymGroup.objects.count()} กลุ่ม"
        ))
        self.stdout.write(
            "\nขั้นต่อไป:\n"
            "  python manage.py createsuperuser        # บัญชีผู้ดูแล\n"
            "  python manage.py make_learner <ชื่อ> --name <ชื่อจริง> "
            "--exam-date YYYY-MM-DD --password '<รหัสที่ตั้งเอง>'\n"
        )
