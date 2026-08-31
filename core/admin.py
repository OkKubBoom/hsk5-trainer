"""Django admin — เฟสแรกใช้แทน UI ทั้งหมด

ได้หน้าจัดการข้อมูลครบทุกตารางโดยไม่เขียน UI แม้แต่หน้าเดียว
นี่คือเหตุผลหลักที่เลือก Django แทน Next.js สำหรับโปรเจกต์นี้
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import (
    AnswerRecord, AudioClip, Card, DailyRecord, DictationAttempt, DrillSession,
    ErrorLog, ExamSpec, GrammarPoint, ItemGroup, LearnerProfile, MockExam,
    Question, QuestionOption, ReviewLog, SynonymGroup, User, VocabItem,
    WritingFeedback, WritingSubmission, WritingTemplate,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "display_name", "role", "email", "is_staff")
    list_filter = ("role", "is_staff", "is_active")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("HSK5 Trainer", {"fields": ("role", "display_name", "timezone")}),
    )


@admin.register(LearnerProfile)
class LearnerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "target_level", "target_exam_date", "days_left",
                    "baseline_badge", "new_words_per_day", "drill_size")
    list_filter = ("target_level", "target_exam_date")
    filter_horizontal = ("coaches",)
    search_fields = ("user__username", "user__display_name")

    @admin.display(description="เหลือกี่วัน")
    def days_left(self, obj):
        return obj.days_to_exam()

    @admin.display(description="คะแนนฐาน")
    def baseline_badge(self, obj):
        if obj.has_baseline:
            return format_html("<b style='color:#3E7A69'>{}</b>", obj.baseline_total)
        return format_html("<b style='color:#B3372C'>ยังไม่ได้วัด</b>")


@admin.register(ExamSpec)
class ExamSpecAdmin(admin.ModelAdmin):
    list_display = ("__str__", "vocab_size", "pass_score", "per_section_minimum", "is_active")
    list_filter = ("standard", "is_active")


@admin.register(VocabItem)
class VocabItemAdmin(admin.ModelAdmin):
    # ลบคำหนึ่งคำ = ลบการ์ดทบทวนและประวัติของทุกคนที่ผูกกับคำนั้นไปด้วย (CASCADE)
    # และกู้คืนไม่ได้ — ถ้าคำผิดให้แก้คำแปล ไม่ใช่ลบทิ้ง
    def has_delete_permission(self, request, obj=None):
        return False

    list_display = ("hanzi", "pinyin", "meaning_th", "hsk_level", "frequency_rank",
                    "standard", "commercial_safe")
    list_filter = ("hsk_level", "standard", "source_type", "commercial_safe")
    search_fields = ("hanzi", "pinyin", "meaning_th", "meaning_en")
    list_per_page = 50
    ordering = ("frequency_rank", "hanzi")


@admin.register(SynonymGroup)
class SynonymGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "item_list")
    filter_horizontal = ("items",)
    search_fields = ("name", "note_th")

    @admin.display(description="คำในกลุ่ม")
    def item_list(self, obj):
        return " / ".join(obj.items.values_list("hanzi", flat=True)[:6])


@admin.register(GrammarPoint)
class GrammarPointAdmin(admin.ModelAdmin):
    list_display = ("title_zh", "title_th", "hsk_level", "section", "priority")
    list_filter = ("hsk_level", "section", "standard")
    search_fields = ("title_zh", "title_th", "explanation_th")


@admin.register(WritingTemplate)
class WritingTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "approx_chars", "use_case", "standard")
    list_filter = ("standard",)


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("vocab", "learner", "card_type", "state", "due_at",
                    "interval_days", "ease", "reps", "lapses")
    list_filter = ("state", "card_type", "learner")
    search_fields = ("vocab__hanzi", "vocab__pinyin")
    raw_id_fields = ("vocab", "learner")
    readonly_fields = ("reps", "lapses", "last_reviewed_at")


@admin.register(ReviewLog)
class ReviewLogAdmin(admin.ModelAdmin):
    list_display = ("card", "reviewed_at", "rating", "prev_interval_days",
                    "new_interval_days", "scheduler_version")
    list_filter = ("rating", "scheduler_version")
    raw_id_fields = ("card",)
    date_hierarchy = "reviewed_at"


@admin.register(AudioClip)
class AudioClipAdmin(admin.ModelAdmin):
    list_display = ("title", "duration_ms", "voice", "speed", "source_type", "commercial_safe")
    list_filter = ("source_type", "commercial_safe", "standard")
    search_fields = ("title", "transcript_zh")


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 4
    fields = ("order", "text", "is_correct", "distractor_type", "rationale_th")


@admin.register(ItemGroup)
class ItemGroupAdmin(admin.ModelAdmin):
    list_display = ("__str__", "kind", "section", "char_count", "difficulty",
                    "source_type", "commercial_safe")
    list_filter = ("kind", "section", "source_type", "commercial_safe", "standard")
    search_fields = ("title", "passage_zh")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("short_prompt", "qtype", "section", "status", "difficulty",
                    "flagged_wrong_count", "commercial_safe")
    list_filter = ("status", "qtype", "section", "source_type", "commercial_safe", "standard")
    search_fields = ("prompt_zh", "answer_text", "explanation_th")
    inlines = [QuestionOptionInline]
    raw_id_fields = ("group", "vocab", "synonym_group", "grammar")
    actions = ["activate", "suspend"]

    @admin.display(description="โจทย์")
    def short_prompt(self, obj):
        return obj.prompt_zh[:60]

    @admin.action(description="เปิดใช้งานข้อที่เลือก")
    def activate(self, request, queryset):
        n = queryset.update(status="active")
        self.message_user(request, f"เปิดใช้งาน {n} ข้อ")

    @admin.action(description="พักข้อที่เลือก (สงสัยเฉลยผิด)")
    def suspend(self, request, queryset):
        n = queryset.update(status="suspended")
        self.message_user(request, f"พัก {n} ข้อ")


class AnswerRecordInline(admin.TabularInline):
    model = AnswerRecord
    extra = 0
    fields = ("question", "card", "given", "is_correct", "error_code", "elapsed_ms")
    readonly_fields = fields
    can_delete = False


@admin.register(DrillSession)
class DrillSessionAdmin(admin.ModelAdmin):
    list_display = ("learner", "started_at", "answered", "correct", "acc", "planned_size")
    list_filter = ("learner",)
    date_hierarchy = "started_at"
    inlines = [AnswerRecordInline]
    readonly_fields = ("mix",)

    @admin.display(description="ความแม่น")
    def acc(self, obj):
        a = obj.accuracy
        return f"{a * 100:.0f}%" if a is not None else "—"


@admin.register(DailyRecord)
class DailyRecordAdmin(admin.ModelAdmin):
    list_display = ("learner", "date", "answered", "correct", "acc",
                    "minutes", "new_words", "cumulative_words", "met_goal")
    list_filter = ("learner", "met_goal")
    date_hierarchy = "date"

    @admin.display(description="ความแม่น")
    def acc(self, obj):
        a = obj.accuracy
        return f"{a * 100:.0f}%" if a is not None else "—"


@admin.register(MockExam)
class MockExamAdmin(admin.ModelAdmin):
    list_display = ("learner", "taken_on", "paper_ref", "listening", "reading",
                    "writing", "total", "passed", "is_timed")
    list_filter = ("learner", "is_timed")
    date_hierarchy = "taken_on"


@admin.register(DictationAttempt)
class DictationAttemptAdmin(admin.ModelAdmin):
    list_display = ("clip", "learner", "accuracy_pct", "replay_count", "playback_rate", "created_at")
    list_filter = ("learner",)
    raw_id_fields = ("clip",)


class WritingFeedbackInline(admin.StackedInline):
    model = WritingFeedback
    extra = 0


@admin.register(WritingSubmission)
class WritingSubmissionAdmin(admin.ModelAdmin):
    list_display = ("learner", "char_count", "meets_length", "minutes_spent", "created_at")
    list_filter = ("learner",)
    inlines = [WritingFeedbackInline]


@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ("label", "learner", "code", "section", "miss_count",
                    "last_seen_at", "is_open", "advice_short")
    list_filter = ("code", "section", "learner", "resolved_at")
    search_fields = ("label",)
    raw_id_fields = ("vocab", "grammar", "question")
    actions = ["mark_resolved"]

    @admin.display(description="ควรทำอะไร")
    def advice_short(self, obj):
        return obj.advice_th[:70]

    @admin.action(description="ทำเครื่องหมายว่าแก้ได้แล้ว")
    def mark_resolved(self, request, queryset):
        from django.utils import timezone
        n = queryset.update(resolved_at=timezone.now())
        self.message_user(request, f"ปิด {n} รายการ")
