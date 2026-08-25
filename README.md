# HSK5 Trainer

ระบบฝึกสอบ HSK ระดับ 5 สำหรับผู้เรียนไทย — เน้นสิ่งที่เครื่องมืออื่นไม่ทำ:
**บันทึกว่าตอบผิดเพราะอะไร แล้วเอาคำตอบนั้นมาปรับชุดข้อสอบวันถัดไป**

> อ่าน [`CLAUDE.md`](CLAUDE.md) ก่อนแก้โค้ด — ในนั้นมีการตัดสินใจทั้งหมดและเหตุผล

---

## เริ่มใช้งาน

```bash
cd ~/Documents/จีน/hsk5-trainer

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # แก้ SECRET_KEY ก่อนขึ้น production

python manage.py migrate
python manage.py seed_hsk5 --learner nong --exam-date 2026-12-13
python manage.py createsuperuser
python manage.py runserver
```

เปิด http://127.0.0.1:8000/admin/

Sprint 1 ยังไม่มีหน้าเว็บสำหรับผู้เรียน — ใช้ Django admin จัดการข้อมูลได้ครบทุกตารางไปก่อน

---

## ทดสอบ

```bash
python manage.py test core
```

25 เทสต์ ครอบคลุมตัวจัดตารางทบทวนและตัวเลือกข้อสอบประจำวัน
สองส่วนนี้ผิดแล้ว **ผิดแบบเงียบ** ผู้เรียนจะไม่รู้ตัวจนกระทั่งสอบตก จึงต้องมีเทสต์คุม

---

## โครงสร้าง

```
config/              settings · urls · wsgi
core/
  models/
    base.py          Provenance · TimeStamped · ErrorCode
    users.py         User · LearnerProfile
    lexicon.py       ExamSpec · VocabItem · SynonymGroup · GrammarPoint · WritingTemplate
    srs.py           Card · ReviewLog
    content.py       AudioClip · ItemGroup · Question · QuestionOption
    practice.py      DrillSession · AnswerRecord · DailyRecord · MockExam ·
                     DictationAttempt · WritingSubmission · WritingFeedback
    diagnostics.py   ErrorLog
  srs.py             ตัวจัดตารางทบทวน  ← ตรรกะอยู่ที่นี่ที่เดียว
  selection.py       Daily Drill Engine ← ตรรกะอยู่ที่นี่ที่เดียว
  admin.py           หน้าจัดการข้อมูลครบทุกตาราง
  management/commands/seed_hsk5.py
data/
  seed_vocab.txt     คำศัพท์ตั้งต้น 109 คำ
  seed_content.json  สเปกข้อสอบ · กลุ่มคำใกล้เคียง · ไวยากรณ์ · เทมเพลต · คำถาม
```

---

## แนวคิดหลักสามข้อ

**1. ชุดข้อสอบขนาดคงที่ ส่วนผสมเปลี่ยน**

50% ถึงกำหนดทบทวน · 30% เคยตอบผิด · 20% ของใหม่

ไอเดียตั้งต้นคือเพิ่มจำนวนข้อวันละ 10% ทบต้น เพื่อให้ของเก่าไม่หาย
เจตนาถูก แต่คณิตศาสตร์ไม่รอด — วันที่ 33 จะมี 211 ข้อ (ชนเพดานเวลา)
และวันสอบจะมี 324,940 ข้อ ทั้งที่ข้อสอบจริงมีแค่ 100 ข้อ

ทางออก: ตรึงเวลาไว้ ให้อัลกอริทึมเลือกว่า *ข้อไหน* ควรออก
ไม่ถามสิ่งที่จำแม่นแล้ว ถามเฉพาะสิ่งที่กำลังจะลืม
ครอบคลุมเท่าเดิม เวลาไม่บาน — ความยากโตแทนจำนวน

**2. ตอบผิดต้องบอกว่าผิดเพราะอะไร**

`VOCAB` ไม่รู้คำ · `MEANING` รู้คำแต่เลือกความหมายผิด · `STRUCTURE` โครงสร้าง ·
`TOO_SLOW` ไม่ทันเวลา · `SOUND` ฟังไม่ออก · `CARELESS` เผลอ

"ผิด 12 ข้อ" ไม่บอกอะไร
"ผิดเพราะไม่ทันเวลา 8 ใน 12" บอกว่าต้องฝึกความเร็ว ไม่ใช่ท่องศัพท์เพิ่ม

**3. ตัวจัดตารางรู้ว่ามีวันสอบ**

SM-2 ออกแบบมาสำหรับการเรียนที่ไม่มีวันสิ้นสุด
ที่นี่มีเส้นตาย — ระยะห่างจึงถูกบีบไม่ให้เกิน 60% ของวันที่เหลือ
การ์ดที่ระบบบอกว่า "เจอกันอีกที 90 วัน" ทั้งที่เหลือ 40 วัน คือการทิ้งคำนั้นไปเลย

---

## ข้อควรระวัง

**ลิขสิทธิ์** — โฟลเดอร์แม่มีข้อสอบเก่า `H51001.pdf` … `H51332.pdf`
ใช้ส่วนตัวได้ **ห้ามนำเข้าฐานข้อมูลเวอร์ชันที่จะขาย**
ทุกอย่างที่ดึงมาจากไฟล์เหล่านั้นต้องตั้ง `source_type="official_past_paper"`
ซึ่งจะบังคับ `commercial_safe=False` ให้อัตโนมัติ (ดู `core/models/base.py`)

**เฉลยผิดแบบเงียบ** — ถ้าคำถามที่ AI สร้างมีเฉลยผิด คำอธิบายจะอธิบายเหตุผล
ของเฉลยที่ผิดอย่างมั่นใจ และผู้เรียนระดับ HSK4 ไม่มีทางจับได้
ทุกคำถามจึงต้องมีปุ่มรายงาน → `Question.flag_wrong_answer()` พักข้อนั้นทันที

---

## ถัดไป

- [ ] Sprint 2 — หน้า Daily Drill (HTMX) + หน้าสถิติผู้เรียน
- [ ] Sprint 3 — พาร์ทฟัง: TTS, เครื่องเล่นปรับความเร็ว, 听写 + เทียบตัวอักษร
- [ ] Sprint 4 — Coach dashboard + สรุปรายสัปดาห์
- [ ] Sprint 5 — deploy VPS + PWA + backup อัตโนมัติ
