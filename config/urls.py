from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.urls import path

admin.site.site_header = "HSK5 Trainer"
admin.site.site_title = "HSK5 Trainer"
admin.site.index_title = "จัดการข้อมูล"


def placeholder(_request):
    """หน้าแรกชั่วคราว — Sprint 2 จะแทนที่ด้วย Daily Drill"""
    return HttpResponse(
        "<h1>HSK5 Trainer</h1>"
        "<p>Sprint 1 เสร็จแล้ว — data model พร้อมใช้</p>"
        "<p><a href='/admin/'>เข้าหน้าจัดการข้อมูล</a></p>",
        content_type="text/html; charset=utf-8",
    )


urlpatterns = [
    path("", placeholder, name="home"),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
