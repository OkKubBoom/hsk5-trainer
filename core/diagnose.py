"""เลือก "สาเหตุ" ของการตอบผิด — หัวใจของ D8 ใน CLAUDE.md

D8 บอกว่า "ทุกครั้งที่ตอบผิดต้องติดป้ายสาเหตุ" และระบุว่านี่คือเหตุผลเดียว
ที่ระบบนี้ควรมีอยู่ เพราะ Anki/Quizlet บอกได้แค่ว่าผิดกี่ข้อ

แต่ของเดิมติดป้ายตายตัว: ข้อคำศัพท์ได้ VOCAB เสมอ ข้ออื่นได้ MEANING เสมอ
รหัส TOO_SLOW / CARELESS / STRUCTURE จึงไม่เคยถูกเขียนลงฐานเลยสักครั้ง
ทั้งที่หน้าสถิติมีช่องรอแสดงอยู่แล้ว

ไฟล์นี้เดาสาเหตุจากสิ่งที่ระบบรู้จริง แล้วเปิดทางให้ผู้เรียนแก้เองได้
เพราะบางสาเหตุระบบแยกไม่ออก — "ไม่รู้คำนี้" กับ "รู้คำแต่เลือกผิด"
มีทางแก้ตรงข้ามกัน (ท่องเพิ่ม vs ห้ามท่องเพิ่ม ให้ไปฝึกอ่านโจทย์)
"""
from __future__ import annotations

from .models import ErrorCode, QuestionType, Section

# ตอบช้ากว่านี้ถือว่า "รู้แต่ไม่ทัน" ไม่ใช่ "ไม่รู้"
# 25 วินาทีมาจากเวลาเป้าหมายของข้ออ่านที่ยาวที่สุด (target_seconds ~70)
# หารสาม เพราะข้อที่รู้จริงควรตอบได้ในหนึ่งในสามของเวลาที่ให้
SLOW_MS = 25_000

# ผู้เรียนกดบอกเองได้ — ป้ายพวกนี้เชื่อถือได้กว่าที่ระบบเดา
SELF_REPORT = {
    ErrorCode.VOCAB: "ไม่รู้คำนี้",
    ErrorCode.MEANING: "รู้คำ แต่เลือกผิด",
    ErrorCode.TOO_SLOW: "รู้ แต่ไม่ทันเวลา",
    ErrorCode.CARELESS: "เผลอกดผิด",
}


def code_for(*, card=None, question=None, elapsed_ms: int = 0) -> str:
    """เดาสาเหตุจากข้อมูลที่มีอยู่แล้ว ไม่ต้องถามผู้เรียน

    ลำดับความสำคัญ: ชนิดของโจทย์มาก่อนเวลา เพราะข้อเรียงคำที่ตอบช้า
    ก็ยังเป็นปัญหาเรื่องลำดับคำอยู่ดี ไม่ใช่ปัญหาความเร็ว
    """
    qtype = getattr(question, "qtype", "") if question else ""

    if qtype == QuestionType.WORD_ORDER:
        return ErrorCode.STRUCTURE
    if question is not None and getattr(question, "section", "") == Section.LISTENING:
        return ErrorCode.SOUND
    if elapsed_ms and elapsed_ms > SLOW_MS:
        return ErrorCode.TOO_SLOW
    if card is not None:
        return ErrorCode.VOCAB
    if qtype == QuestionType.SYNONYM_CLOZE:
        # 阅读第一部分 วัดการแยกคำใกล้เคียงโดยเฉพาะ ผิดที่นี่คือปัญหาคำศัพท์
        return ErrorCode.VOCAB
    return ErrorCode.MEANING
