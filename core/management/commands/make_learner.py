"""สร้างบัญชีผู้เรียนหนึ่งคน พร้อมการ์ดทบทวนจากคำศัพท์ทั้งคลัง

    python manage.py make_learner mint --name มิ้นท์ --exam-date 2026-11-07
    python manage.py make_learner bell --name เบล --exam-date 2026-12-13 --coach supakit

รันซ้ำได้ — ถ้ามีบัญชีอยู่แล้วจะอัปเดตวันสอบและเติมการ์ดที่ยังขาด
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Card, CardType, LearnerProfile, Role, User, VocabItem


class Command(BaseCommand):
    help = "สร้าง/อัปเดตผู้เรียน พร้อมสร้างการ์ดทบทวนให้ครบทุกคำในคลัง"

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--name", default="", help="ชื่อที่แสดงในระบบ")
        # ไม่มีค่าตั้งต้นโดยตั้งใจ — รหัสผ่านที่เขียนไว้ในโค้ดสาธารณะคือรหัสที่ทุกคนรู้
        parser.add_argument("--password", required=True,
                            help="รหัสผ่านตั้งต้น (อย่างน้อย 8 ตัวอักษร) — ต้องตั้งเอง")
        parser.add_argument("--exam-date", required=True, help="YYYY-MM-DD")
        parser.add_argument("--backup-exam-date", default=None, help="วันสอบสำรอง YYYY-MM-DD")
        parser.add_argument("--coach", default=None, help="username ของโค้ชที่ดูข้อมูลได้")

    @transaction.atomic
    def handle(self, *args, **opts):
        if len(opts["password"]) < 8:
            self.stderr.write("รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร")
            return

        user, created = User.objects.get_or_create(
            username=opts["username"],
            defaults={"first_name": opts["name"], "role": Role.LEARNER},
        )
        if created or opts.get("password"):
            user.set_password(opts["password"])
        if opts["name"]:
            user.first_name = opts["name"]
        user.save()

        profile, _ = LearnerProfile.objects.get_or_create(
            user=user,
            defaults={"target_exam_date": date.fromisoformat(opts["exam_date"])},
        )
        profile.target_exam_date = date.fromisoformat(opts["exam_date"])
        if opts["backup_exam_date"]:
            profile.backup_exam_date = date.fromisoformat(opts["backup_exam_date"])
        profile.save()

        if opts["coach"]:
            coach = User.objects.filter(username=opts["coach"]).first()
            if coach:
                profile.coaches.add(coach)

        # การ์ดหนึ่งใบต่อหนึ่งคำ (ชนิด "อ่านแล้วรู้ความหมาย")
        # ชนิดฟังจะเพิ่มตอนมีไฟล์เสียงในเฟส 3 ไม่สร้างล่วงหน้าให้กองรอเปล่าๆ
        existing = set(Card.objects.filter(learner=profile).values_list("vocab_id", flat=True))
        new_cards = [
            Card(learner=profile, vocab=v, card_type=CardType.RECOGNIZE)
            for v in VocabItem.objects.exclude(meaning_th="").only("id")
            if v.pk not in existing
        ]
        Card.objects.bulk_create(new_cards, batch_size=500)

        self.stdout.write(self.style.SUCCESS(
            f"ผู้เรียน {user.username} ({user.first_name or '-'}) · สอบ {profile.target_exam_date} · "
            f"สร้างการ์ดใหม่ {len(new_cards)} ใบ (รวม {Card.objects.filter(learner=profile).count()} ใบ)"
        ))
