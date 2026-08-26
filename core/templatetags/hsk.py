"""ตัวช่วยเล็กๆ สำหรับเทมเพลต — เอาไว้แสดงผลอย่างเดียว ห้ามใส่ตรรกะธุรกิจ"""
from django import template

register = template.Library()

TOTAL_PAPERS = 9


@register.filter
def paper_dots(count):
    """แปลง 'พบใน 7 ชุด' เป็นจุด 9 จุด — กวาดสายตาเห็นทันทีโดยไม่ต้องอ่านตัวเลข"""
    try:
        n = int(count or 0)
    except (TypeError, ValueError):
        n = 0
    return [i < n for i in range(TOTAL_PAPERS)]


@register.filter
def trap_ratio(word):
    """สัดส่วนความเป็นตัวลวง — ใช้ระบายแถบให้เห็นว่าคำไหนหลอกมากกว่าเป็นคำตอบ"""
    lure = getattr(word, "exam_as_distractor", 0) or 0
    ans = getattr(word, "exam_as_answer", 0) or 0
    total = lure + ans
    return round(lure / total * 100) if total else 0


@register.filter
def rank_class(index):
    """สามอันดับแรกเน้นให้เห็น — ที่เหลือเรียบ"""
    return "rank top" if index <= 3 else "rank"
