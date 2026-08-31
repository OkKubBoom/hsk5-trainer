"""สำรองข้อมูลของผู้เรียนออกมาเป็นไฟล์

    python manage.py backup                    # เขียนลง backups/
    python manage.py backup --out /path/to/dir

สำรองทั้งฐานข้อมูล ยกเว้นตารางที่ Django สร้างใหม่เองได้
ทดสอบกู้คืนใส่ฐานเปล่าแล้วว่าได้จริง

ที่ต้องมีเพราะ core/models/srs.py:83 เขียนไว้เองว่า ReviewLog "ห้ามลบ"
แต่ทั้งระบบไม่มีการสำรองอะไรเลยแม้แต่บรรทัดเดียว ถ้าฐานข้อมูลหายวันที่ 50
คิว SRS กับบันทึกข้อผิดหายหมด = เริ่มนับหนึ่งใหม่ในช่วงที่ไม่มีเวลาเริ่มใหม่

กู้คืนด้วย:
    python manage.py loaddata backups/<ไฟล์>.json
"""
from datetime import datetime
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

# สำรองทั้งฐาน ยกเว้นตารางที่ Django สร้างใหม่เองได้
#
# เคยลองสำรองเฉพาะข้อมูลผู้เรียนแล้วกู้ไม่ได้จริง เพราะการ์ดอ้างถึงคำศัพท์
# ที่ไม่ได้อยู่ในไฟล์ ต่อให้รัน bootstrap ก่อนก็ยังเสี่ยง เพราะเลข id
# ต้องตรงกันเป๊ะ ซึ่งไม่มีอะไรรับประกัน
#
# ไฟล์ใหญ่ขึ้นแต่กู้คืนได้จริง ซึ่งเป็นสิ่งเดียวที่การสำรองมีไว้เพื่อ
EXCLUDE = [
    "contenttypes",          # Django สร้างเองตอน migrate
    "auth.Permission",       # ผูกกับ contenttypes
    "sessions",              # เซสชันหมดอายุอยู่แล้ว กู้ไปก็ไม่มีประโยชน์
    "admin.LogEntry",        # ประวัติการกดในหน้า admin ไม่ใช่ข้อมูลผู้เรียน
]


class Command(BaseCommand):
    help = "สำรองประวัติการฝึกของผู้เรียนออกเป็นไฟล์ JSON"

    def add_arguments(self, parser):
        parser.add_argument("--out", default="backups", help="โฟลเดอร์ปลายทาง")
        parser.add_argument("--keep", type=int, default=14,
                            help="เก็บไฟล์ย้อนหลังกี่ไฟล์ (เกินนั้นลบตัวเก่าสุด)")

    def handle(self, *args, **opts):
        out_dir = Path(opts["out"])
        out_dir.mkdir(parents=True, exist_ok=True)

        stamp = timezone.localtime().strftime("%Y-%m-%d_%H%M")
        path = out_dir / f"hsk5-backup-{stamp}.json"

        with path.open("w", encoding="utf-8") as f:
            call_command(
                "dumpdata", exclude=EXCLUDE,
                natural_foreign=True, indent=1, stdout=f,
            )

        size_kb = path.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(f"สำรองแล้ว → {path} ({size_kb:,.0f} KB)"))

        self._prune(out_dir, opts["keep"])
        self.stdout.write(
            "\nกู้คืนด้วย:  python manage.py loaddata " + str(path) +
            "\nแนะนำให้ลองกู้คืนใส่ฐานข้อมูลเปล่าหนึ่งครั้ง — "
            "การสำรองที่ไม่เคยทดสอบกู้คืน ไม่นับว่ามีการสำรอง"
        )

    def _prune(self, out_dir: Path, keep: int):
        files = sorted(out_dir.glob("hsk5-backup-*.json"))
        for old in files[:-keep] if keep > 0 else []:
            old.unlink()
            self.stdout.write(f"  ลบไฟล์เก่า {old.name}")
