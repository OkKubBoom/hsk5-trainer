"""เซสชันหมดอายุทุกเที่ยงคืน + บันทึกว่าใครเข้าระบบวันไหนบ้าง

ทำไมต้องเตะออกตอนเที่ยงคืน: เจ้าของระบบอยากรู้ว่าผู้เรียน "เข้ามาใหม่ทุกวัน" จริงไหม
ถ้าเซสชันค้างอยู่เป็นเดือน การเข้าระบบครั้งเดียวจะดูเหมือนใช้งานตลอด

สองส่วนนี้แยกกันโดยตั้งใจ:
  - การ *บันทึก* วันเข้าระบบ ทำงานเสมอ ไม่ขึ้นกับว่าจะเตะออกหรือไม่
  - การ *เตะออก* ปิดได้ด้วย DJANGO_DAILY_LOGOUT=0 โดยที่สถิติยังครบเหมือนเดิม

แยกแบบนี้เพราะการบังคับพิมพ์รหัสผ่านใหม่ทุกวันมีต้นทุน — ความเสียดทานรายวัน
คือสาเหตุอันดับต้นๆ ที่คนเลิกทำอะไรที่ตั้งใจทำทุกวัน ถ้าวันหนึ่งพบว่าน้องเริ่มขี้เกียจ
เพราะต้องล็อกอินใหม่ ให้ปิดสวิตช์ตัวนี้ได้เลย ตัวเลข "เข้าระบบกี่วัน" จะยังอยู่ครบ
"""
from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

SESSION_DAY_KEY = "login_day"


@receiver(user_logged_in)
def stamp_login_day(sender, request, user, **kwargs):
    """จำไว้ว่าเซสชันนี้เกิดขึ้นวันไหน + บันทึกลงฐานข้อมูล

    เขียนวันลงเซสชันเอง แทนที่จะพึ่ง SESSION_COOKIE_AGE เพราะอายุคุกกี้นับเป็น
    "กี่วินาทีนับจากล็อกอิน" ซึ่งไม่ตรงกับ "หมดอายุตอนเที่ยงคืน" ที่ต้องการ
    ล็อกอินสี่ทุ่มจะได้อยู่ถึงเที่ยงคืน ไม่ใช่อยู่ถึงสี่ทุ่มวันรุ่งขึ้น
    """
    from .models import LoginDay

    today = timezone.localdate()
    if request is not None:
        request.session[SESSION_DAY_KEY] = today.isoformat()
    LoginDay.objects.get_or_create(user=user, date=today)


class DailyLogoutMiddleware:
    """เตะออกเมื่อข้ามวัน — เทียบวันที่ ไม่ใช่นับชั่วโมง"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._expired(request):
            logout(request)
            messages.info(request, "ขึ้นวันใหม่แล้ว — เข้าสู่ระบบอีกครั้งเพื่อเริ่มชุดของวันนี้")
            return redirect(f"{reverse('login')}?next={request.path}")
        return self.get_response(request)

    def _expired(self, request) -> bool:
        if not getattr(settings, "DAILY_LOGOUT", True):
            return False
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        # ยกเว้นหน้าที่ไม่ได้ล็อกอินก็เข้าได้ ไม่งั้นจะวนกลับมาที่ตัวเอง
        if request.path.startswith(("/login", "/logout", "/version", "/static", "/admin/login")):
            return False

        stamped = request.session.get(SESSION_DAY_KEY)
        if not stamped:
            # เซสชันเก่าที่เกิดก่อนมีระบบนี้ — ประทับวันนี้ให้ ไม่เตะออก
            # ไม่งั้นทุกคนจะโดนเตะพร้อมกันตอน deploy โดยไม่รู้สาเหตุ
            request.session[SESSION_DAY_KEY] = timezone.localdate().isoformat()
            return False
        return stamped != timezone.localdate().isoformat()
