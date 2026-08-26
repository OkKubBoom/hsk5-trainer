from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "HSK5 Trainer"
admin.site.site_title = "HSK5 Trainer"
admin.site.index_title = "จัดการข้อมูล"

urlpatterns = [
    path("", include("core.urls")),
    # หน้าจัดการข้อมูลสำหรับเจ้าของ/ครูเท่านั้น ผู้เรียนไม่ได้ใช้หน้านี้
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
