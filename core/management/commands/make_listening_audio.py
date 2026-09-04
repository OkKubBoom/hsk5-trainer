"""สร้างไฟล์เสียงข้อฟังด้วย Kokoro — รันบนเครื่องพัฒนาเท่านั้น

    python manage.py make_listening_audio            # ดูว่าจะสร้างกี่ไฟล์
    python manage.py make_listening_audio --apply    # สร้างจริง

**ทำไมอัดไฟล์ไว้ ไม่ให้เบราว์เซอร์อ่านสด**
  เสียงดีกว่ามาก — ตัวอ่านของเบราว์เซอร์เป็นเสียงสังเคราะห์รุ่นเก่า
  ทุกคนได้ยินเหมือนกัน — เดิมเสียงขึ้นกับว่าใครเปิดจากเครื่องอะไร คุมไม่ได้เลย
  มีผู้พูดสองคนจริง — เดิมมีเสียงเดียว ต้องปลอมเป็นผู้ชายด้วยการลดระดับเสียง

**เครื่องมือที่ต้องมี** (ไม่ได้อยู่ใน requirements เพราะเซิร์ฟเวอร์ไม่ต้องใช้)
    pip install sherpa-onnx soundfile numpy
    ดาวน์โหลด kokoro-int8-multi-lang-v1_1 จาก
    https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models
    แตกไฟล์ไว้ที่ data/tts/kokoro-int8-multi-lang-v1_1/  (อยู่ใน .gitignore)

**ความเร็วและจังหวะวัดจากไฟล์เสียงข้อสอบจริง** ไม่ได้ตั้งเอง — ดูค่าคงที่ข้างล่าง

**เสียงที่เลือก** เจ้าของระบบฟังเทียบ 12 เสียงแล้วเลือกเอง — หญิง 28 · ชาย 81
วัดได้ว่าห่างกัน 117 Hz ซึ่งมากพอให้แยกออกว่าใครพูด (คำถาม 男的/女的 ต้องใช้)

**บทเล่าเรื่อง (ข้อ 36-45) สลับเพศผู้บรรยายตามเลขข้อ**
ข้อสอบจริงใช้ทั้งผู้บรรยายชายและหญิง ถ้าใช้เสียงเดียวตลอด ผู้เรียนจะชินกับเสียงนั้น
แล้วเจอผู้บรรยายชายในห้องสอบจริงจะฟังยากขึ้นทันที ทั้งที่ซ้อมมาแล้วเป็นร้อยข้อ
สลับตามเลขข้อ ไม่ใช่สุ่ม เพื่อให้สร้างไฟล์ใหม่กี่ครั้งก็ได้ผลเดิม

⚠️ ลิขสิทธิ์ — เสียงที่ได้แปลงจากบทข้อสอบจริง จึงเป็นของลิขสิทธิ์เหมือนตัวบท
ใช้ฝึกส่วนตัวได้ ห้ามเข้าเวอร์ชันขาย (D6) ต่อให้ตัวโมเดล Kokoro จะเป็น Apache-2.0
"""
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from core import listening as parser
from core.models import Question, QuestionStatus, Section

MODEL_DIR = Path(settings.BASE_DIR) / "data" / "tts" / "kokoro-int8-multi-lang-v1_1"
OUT_DIR = Path(settings.BASE_DIR) / "static" / "listening"

FEMALE_SID, MALE_SID = 28, 81

# ── ตัวเลขทั้งหมดข้างล่างวัดจากไฟล์เสียงข้อสอบจริง H51001 (30 นาที 17 วินาที) ──
#
# วิธีวัด: แปลงเป็น wav → หาช่วงที่มีเสียงด้วยพลังงานต่อหน้าต่าง 20 ms
# → เอาจำนวนตัวอักษรจีนหารด้วยเวลาที่ *มีเสียงพูดจริง* (ไม่นับช่วงเงียบ)
#
# ⚠️ กับดักที่เกือบทำพลาด: บทยาวข้อ 31-45 ต้นฉบับอ่าน *ครั้งเดียว* ต่อกลุ่ม
# แต่ไฟล์ของเราอ่านซ้ำทุกข้อที่ใช้บทนั้น ถ้านับตัวอักษรฝั่งต้นฉบับแบบเดียวกับของเรา
# จะได้ว่าต้นฉบับพูดเร็วกว่า ทั้งที่ความจริงคือ *ช้ากว่า* — ต้องนับบทยาวครั้งเดียว
#
# ผลที่วัดได้ (ตัวอักษรจีนต่อวินาทีของเวลาที่มีเสียง):
#   ต้นฉบับ พาร์ท 1  ~3.2   ต้นฉบับ พาร์ท 2  3.65   รวม 3.43
#   ของเราตอนนั้น    4.52  → เร็วกว่าข้อสอบจริง 1.3 เท่า
PART1_SPEED = 0.71          # ข้อ 1-20 บทสนทนาสั้น ต้นฉบับอ่านช้าและชัดกว่า
PART2_SPEED = 0.81          # ข้อ 21-45 บทยาว ต้นฉบับอ่านกระชับขึ้น
QUESTION_SPEED_RATIO = 0.94  # คำถามเป็นเสียงผู้บรรยาย ช้ากว่าคู่สนทนานิดหนึ่ง

# ช่วงเงียบในข้อเดียวกันของต้นฉบับ: กลาง 0.58 วิ · 75% อยู่ที่ 0.88 วิ
GAP_TURN, GAP_QUESTION = 0.55, 0.90

# ช่วงให้ฝนคำตอบของจริงคือ 16.2 วินาที (วัดได้ 45 ครั้งพอดี = 45 ข้อ)
# **ไม่ใส่ในไฟล์โดยตั้งใจ** — ข้อสอบต้องมีเพราะเทปหยุดไม่ได้ แต่ระบบเรา
# ให้ผู้เรียนกดเองว่าจะไปข้อต่อไปเมื่อไหร่ ใส่ไปจะกลายเป็นเวลาตายที่ต้องนั่งรอเปล่าๆ
REAL_ANSWER_GAP = 16.2

BITRATE = "32000"           # AAC โมโน — เสียงพูดที่ 32k ฟังไม่ออกว่าถูกบีบ


class Command(BaseCommand):
    help = "สร้างไฟล์เสียงข้อฟังด้วย Kokoro (เครื่องพัฒนาเท่านั้น)"

    def add_arguments(self, parser_):
        parser_.add_argument("--apply", action="store_true", help="สร้างจริง")
        parser_.add_argument("--force", action="store_true", help="สร้างทับไฟล์เดิม")

    def handle(self, *args, **opts):
        rows = list(
            Question.objects
            .filter(section=Section.LISTENING, status=QuestionStatus.ACTIVE)
            .exclude(audio_turns=[]).order_by("source_ref")
        )
        todo = [q for q in rows
                if opts["force"] or not (OUT_DIR / f"{parser.audio_slug(q.source_ref)}.m4a").exists()]

        self.stdout.write(f"ข้อฟังที่พร้อม {len(rows)} ข้อ · ยังไม่มีไฟล์ {len(todo)} ข้อ")
        if not opts["apply"]:
            self.stdout.write("เติม --apply เพื่อสร้างจริง")
            return
        if not todo:
            self.stdout.write(self.style.SUCCESS("มีไฟล์ครบแล้ว ไม่ต้องทำอะไร"))
            return
        if not MODEL_DIR.is_dir():
            self.stderr.write(f"ไม่พบโมเดลที่ {MODEL_DIR} — อ่านวิธีติดตั้งที่หัวไฟล์นี้")
            return

        tts, sr = self._engine()
        OUT_DIR.mkdir(parents=True, exist_ok=True)

        for n, question in enumerate(todo, start=1):
            self._render(tts, sr, question)
            if n % 25 == 0 or n == len(todo):
                self.stdout.write(f"  {n}/{len(todo)}")

        total = sum(f.stat().st_size for f in OUT_DIR.glob("*.m4a"))
        self.stdout.write(self.style.SUCCESS(
            f"เสร็จ — ไฟล์ทั้งหมด {len(list(OUT_DIR.glob('*.m4a')))} · {total / 1024 / 1024:.1f} MB"
        ))

    def _narrator(self, source_ref: str) -> int:
        """ผู้บรรยายของข้อนี้ — สลับชายหญิงตามเลขข้อ

        ใช้เลขข้อ ไม่ใช่การสุ่ม เพราะต้องสร้างไฟล์ใหม่แล้วได้ผลเดิมทุกครั้ง
        ไม่งั้นไฟล์ที่สร้างคนละรอบจะเสียงไม่เหมือนกันโดยไม่มีใครรู้
        """
        slug = parser.audio_slug(source_ref)
        try:
            number = int(slug.rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            return FEMALE_SID
        return MALE_SID if number % 2 else FEMALE_SID

    def _part_speed(self, source_ref: str) -> float:
        """ความเร็วของพาร์ทที่ข้อนี้อยู่ — วัดจากข้อสอบจริง ไม่ได้ตั้งเอง

        ข้อสอบจริงพาร์ท 1 อ่านช้ากว่าพาร์ท 2 ชัดเจน เพราะเป็นบทสนทนาสั้น
        ที่ต้องจับใจความให้ทันในรอบเดียว ถ้าใช้ความเร็วเดียวทั้งฉบับ
        พาร์ท 1 จะยากเกินจริง และพาร์ท 2 จะง่ายเกินจริง
        """
        slug = parser.audio_slug(source_ref)
        try:
            number = int(slug.rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            return PART2_SPEED
        return PART1_SPEED if number <= 20 else PART2_SPEED

    def _engine(self):
        import sherpa_onnx

        d = str(MODEL_DIR)
        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=f"{d}/model.int8.onnx", voices=f"{d}/voices.bin",
                    tokens=f"{d}/tokens.txt",
                    lexicon=f"{d}/lexicon-zh.txt,{d}/lexicon-us-en.txt",
                    data_dir=f"{d}/espeak-ng-data", dict_dir=f"{d}/dict", lang="zh"),
                num_threads=6),
            rule_fsts=f"{d}/phone-zh.fst,{d}/date-zh.fst,{d}/number-zh.fst",
            max_num_sentences=1)
        tts = sherpa_onnx.OfflineTts(cfg)
        return tts, tts.sample_rate

    def _render(self, tts, sr, question):
        import numpy as np
        import soundfile as sf

        turns = question.audio_turns or []
        narrator = self._narrator(question.source_ref)
        base = self._part_speed(question.source_ref)
        chunks = []
        for i, turn in enumerate(turns):
            sid = {"m": MALE_SID, "f": FEMALE_SID}.get(turn["who"], narrator)
            speed = base * (QUESTION_SPEED_RATIO if turn["who"] == "q" else 1.0)
            audio = tts.generate(turn["text"], sid=sid, speed=speed)
            chunks.append(np.asarray(audio.samples, dtype=np.float32))

            nxt = turns[i + 1] if i + 1 < len(turns) else None
            if nxt:
                gap = GAP_QUESTION if nxt["who"] == "q" else GAP_TURN
                chunks.append(np.zeros(int(gap * sr), dtype=np.float32))

        out = OUT_DIR / f"{parser.audio_slug(question.source_ref)}.m4a"
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, np.concatenate(chunks), sr)
            # afconvert มากับ macOS อยู่แล้ว ไม่ต้องลง ffmpeg เพิ่ม
            subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", BITRATE,
                            "-c", "1", tmp.name, str(out)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            Path(tmp.name).unlink(missing_ok=True)
