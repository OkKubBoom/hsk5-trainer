"""หน้าเว็บของผู้เรียน — บางที่สุดเท่าที่ทำได้

ตรรกะทั้งหมดอยู่ที่ srs.py / selection.py / placement.py / drill.py
ไฟล์นี้แค่รับคำขอ เรียกตรรกะ แล้วส่งค่าไปให้เทมเพลต (CLAUDE.md ข้อ 11)
"""
from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import diagnose
from . import essay as essay_engine
from . import essay_grader
from . import drill as drill_engine
from . import grammar as grammar_engine
from . import progress as progress_engine
from . import writing as writing_engine
from . import mock as mock_engine
from . import reading as reading_engine
from . import review as review_engine
from . import version as version_info
from .accounts import create_learner
from . import placement as placement_engine
from . import selection, srs
from .models import (
    Card, DrillSession, ErrorCode, ErrorLog, LearnerProfile,
    ExplanationNote, MockExam, NoteStatus, NoteVerdict, PlacementTest, Question,
    ReviewMode, ReviewPhase, ReviewSession, Role, SynonymGroup, User, VocabItem,
    WritingFeedback, WritingSubmission,
)

DRILL_SESSION_KEY = "drill_session_id"


def version(request):
    """เวอร์ชันที่กำลังให้บริการ — เปิดได้โดยไม่ต้องล็อกอิน

    ตั้งใจไม่บังคับล็อกอิน เพราะประโยชน์หลักคือเช็คตอน deploy ว่าโค้ดขึ้นหรือยัง
    ซึ่งต้องทำได้เร็วจากมือถือ และข้อมูลในนี้ไม่มีอะไรเป็นความลับ
    """
    from django.http import JsonResponse
    return JsonResponse(version_info.as_dict(), json_dumps_params={"ensure_ascii": False})


def _learner(request) -> LearnerProfile | None:
    return LearnerProfile.objects.filter(user=request.user).first()


def learner_required(view):
    """view ที่ทำงานไม่ได้ถ้าไม่มีโปรไฟล์ผู้เรียน

    บัญชีผู้ดูแลไม่มี LearnerProfile — เดิม 25 view เรียก _learner() แล้วใช้ต่อทันที
    ทำให้ทุกหน้ายกเว้นหน้าแรกพัง 500 เมื่อเจ้าของระบบกดเข้าไปดู
    ซึ่งเป็นสิ่งที่เจ้าของระบบทำบ่อยที่สุดเวลาตรวจว่าน้องเห็นอะไร
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not _learner(request):
            return render(request, "core/no_profile.html", {"nav": ""})
        return view(request, *args, **kwargs)
    return wrapper


@login_required
def home(request):
    learner = _learner(request)
    if not learner:
        return render(request, "core/no_profile.html", {"nav": "home"})

    summary = selection.today_summary(learner)
    last_placement = learner.placement_tests.filter(finished_at__isnull=False).first()
    today = timezone.localdate()
    today_session = (
        DrillSession.objects.filter(learner=learner, started_at__date=today)
        .order_by("-started_at").first()
    )
    return render(request, "core/home.html", {
        "nav": "home",
        "learner": learner,
        "summary": summary,
        "placement": last_placement,
        "today_session": today_session,
    })


# ── แบบวัดระดับ ────────────────────────────────────────────

@login_required
@learner_required
def placement_start(request):
    learner = _learner(request)
    test = learner.placement_tests.filter(finished_at__isnull=True).first()
    if not test:
        test = placement_engine.start(learner, size=80)
    return redirect("placement_run", test_id=test.pk)


@login_required
@learner_required
def placement_run(request, test_id):
    learner = _learner(request)
    test = get_object_or_404(PlacementTest, pk=test_id, learner=learner)
    if test.is_done:
        return redirect("placement_result", test_id=test.pk)

    vocab = placement_engine.next_vocab(test)
    if vocab is None:
        placement_engine.finish(test)
        return redirect("placement_result", test_id=test.pk)

    question = placement_engine.make_question(vocab)
    return render(request, "core/placement.html", {
        "test": test,
        "vocab": vocab,
        "question": question,
        "answered": test.answered_count,
        "total": test.planned_size,
    })


@login_required
@learner_required
@require_POST
def placement_answer(request, test_id):
    learner = _learner(request)
    test = get_object_or_404(PlacementTest, pk=test_id, learner=learner)
    vocab = get_object_or_404(VocabItem, pk=request.POST.get("vocab_id"))
    placement_engine.record(
        test, vocab,
        given=request.POST.get("given", ""),
        said_unknown=request.POST.get("unknown") == "1",
        elapsed_ms=int(request.POST.get("elapsed_ms") or 0),
    )
    return redirect("placement_run", test_id=test.pk)


@login_required
@learner_required
def placement_result(request, test_id):
    learner = _learner(request)
    test = get_object_or_404(PlacementTest, pk=test_id, learner=learner)
    if not test.is_done:
        placement_engine.finish(test)
        test.refresh_from_db()
    levels = [
        {"level": lv, **data}
        for lv, data in sorted((test.result.get("by_level") or {}).items())
    ]
    return render(request, "core/placement_result.html", {
        "nav": "home", "test": test, "result": test.result, "levels": levels, "learner": learner,
    })


# ── ชุดฝึกรายวัน ───────────────────────────────────────────

@login_required
@learner_required
def drill_start(request):
    """เริ่มชุดของวันนี้ — ถ้าทำไปแล้วจะพาไปดูสรุปแทน ไม่สร้างชุดใหม่"""
    learner = _learner(request)
    session, created = drill_engine.start_or_resume(learner)
    if not created and session.is_finished:
        messages.info(request, "วันนี้ทำชุดไปแล้ว — หนึ่งวันหนึ่งชุด เพื่อให้สถิติสะท้อนความจริง")
        return redirect("drill_done", session_id=session.pk)
    request.session[DRILL_SESSION_KEY] = session.pk
    return redirect("drill_run")


@login_required
@learner_required
def drill_run(request):
    learner = _learner(request)
    session = drill_engine.today_session(learner)
    if not session:
        return redirect("home")
    if session.is_finished:
        return redirect("drill_done", session_id=session.pk)

    entry = drill_engine.current_entry(session)
    if entry is None:
        drill_engine.finish(session)
        return redirect("drill_done", session_id=session.pk)

    total = len(session.queue or [])
    question = drill_engine.build_question(entry, session.position + 1, total)
    if question is None:  # ข้อที่แสดงไม่ได้ (ถูกลบ/ไม่มีตัวเลือก) — ข้ามไป
        drill_engine.advance(session)
        return redirect("drill_run")

    return render(request, "core/drill.html", {
        "session": session, "q": question, "learner": learner,
        "source_label": drill_engine.SOURCE_LABEL.get(question.source, ""),
        "source_why": drill_engine.SOURCE_WHY.get(question.source, ""),
        "progress": round((session.position / total) * 100) if total else 0,
    })


@login_required
@learner_required
@require_POST
def drill_answer(request):
    learner = _learner(request)
    session = drill_engine.today_session(learner)
    if not session or session.is_finished:
        return redirect("home")

    entry = drill_engine.current_entry(session)
    if entry is None:
        return redirect("drill_run")

    outcome = drill_engine.submit(
        session, entry,
        given=request.POST.get("given", ""),
        correct_answer=request.POST.get("answer", ""),
        elapsed_ms=int(request.POST.get("elapsed_ms") or 0),
    )
    drill_engine.advance(session)
    return render(request, "core/partials/feedback.html", {
        "outcome": outcome,
        "given": request.POST.get("given", ""),
        "is_last": session.position >= len(session.queue or []),
        # ตัวเลือกที่ผู้เรียนกดบอกเองได้ — สั้นกว่ารายการเต็มเพราะต้องตัดสินใจใน 1 วินาที
        "reason_choices": list(diagnose.SELF_REPORT.items()),
    })


@login_required
@learner_required
@require_POST
def error_reason(request, log_id):
    """ผู้เรียนกดบอกเองว่าผิดเพราะอะไร — ทับค่าที่ระบบเดาไว้

    ระบบเดาได้แค่จากชนิดโจทย์กับเวลาที่ใช้ แต่แยกไม่ออกระหว่าง
    "ไม่รู้คำนี้" กับ "รู้คำแต่เลือกผิด" ซึ่งมีทางแก้ตรงข้ามกัน
    (ท่องเพิ่ม vs ห้ามท่องเพิ่ม ให้ไปฝึกอ่านโจทย์)
    """
    learner = _learner(request)
    log = get_object_or_404(ErrorLog, pk=log_id, learner=learner)
    code = request.POST.get("code", "")
    if code in dict(ErrorCode.choices):
        log.code = code
        log.save(update_fields=["code", "updated_at"])
    return render(request, "core/partials/reason_thanks.html", {
        "advice": ErrorCode.advice(log.code),
    })


@login_required
@learner_required
def drill_done(request, session_id):
    learner = _learner(request)
    session = get_object_or_404(DrillSession, pk=session_id, learner=learner)
    if not session.is_finished and session.remaining == 0:
        drill_engine.finish(session)
    wrong = session.answers.filter(is_correct=False).select_related("card__vocab", "question")
    return render(request, "core/drill_done.html", {
        "nav": "home", "session": session, "wrong": wrong, "learner": learner,
        "is_today": session.started_at.date() == timezone.localdate(),
    })


# ── ทบทวนอิสระ ─────────────────────────────────────────────

def _review_filters(request) -> dict:
    """อ่านตัวกรองสามแกนจาก query string — ค่าที่ไม่รู้จักถือว่าไม่ได้กรอง"""
    tier = request.GET.get("tier", "")
    window = request.GET.get("window", "")
    level = request.GET.get("level", "")
    return {
        "tier": tier if tier in review_engine.TIERS else "",
        "window": int(window) if window.isdigit() and int(window) in review_engine.WINDOWS else 0,
        "level": int(level) if level.isdigit() and 1 <= int(level) <= 6 else 0,
    }


@login_required
def review_home(request):
    learner = _learner(request)
    if not learner:
        return render(request, "core/no_profile.html", {"nav": "memorize"})

    f = _review_filters(request)
    pool = review_engine.build_pool(learner, **f)
    drill_today = drill_engine.today_session(learner)

    return render(request, "core/review_home.html", {
        "nav": "memorize", "learner": learner,
        "tiers": review_engine.tier_counts(learner, window=f["window"], level=f["level"]),
        "levels": review_engine.level_counts(learner, window=f["window"]),
        "windows": review_engine.WINDOWS.items(),
        "sizes": review_engine.SIZE_CHOICES,
        "modes": ReviewMode.choices,
        "available": pool.count(),
        "running": review_engine.running(learner),
        "stats": review_engine.stats(learner),
        # เตือนให้ทำชุดหลักก่อน — ทบทวนอิสระเสริมได้ แต่แทนกันไม่ได้
        "drill_pending": drill_today is None or not drill_today.is_finished,
        **f,
    })


@login_required
@learner_required
@require_POST
def review_start(request):
    learner = _learner(request)
    size = int(request.POST.get("size") or review_engine.DEFAULT_SIZE)
    mode = request.POST.get("mode", ReviewMode.MEANING)
    session = review_engine.start(
        learner,
        tier=request.POST.get("tier", ""),
        window=int(request.POST.get("window") or 0),
        level=int(request.POST.get("level") or 0),
        size=size if size in review_engine.SIZE_CHOICES else review_engine.DEFAULT_SIZE,
        mode=mode if mode in ReviewMode.values else ReviewMode.MEANING,
    )
    if session is None:
        messages.info(request, "ยังไม่มีคำที่เข้าเงื่อนไขนี้ — ลองผ่อนตัวกรองลง")
        return redirect("review_home")
    return redirect("review_study", session_id=session.pk)


@login_required
@learner_required
def review_study(request, session_id):
    """ขั้นดูคำ — เห็นทั้งชุดพร้อมความหมายก่อน แล้วกดเองว่าพร้อม"""
    learner = _learner(request)
    session = get_object_or_404(ReviewSession, pk=session_id, learner=learner)
    if session.finished_at:
        return redirect("review_done", session_id=session.pk)
    if session.phase != ReviewPhase.STUDY:
        # กดเริ่มทดสอบไปแล้ว ห้ามย้อนกลับมาเปิดดูเฉลย
        return redirect("review_run", session_id=session.pk)

    return render(request, "core/review_study.html", {
        "nav": "memorize", "session": session, "learner": learner,
        "cards": review_engine.study_cards(session),
    })


@login_required
@learner_required
@require_POST
def review_begin_test(request, session_id):
    learner = _learner(request)
    session = get_object_or_404(ReviewSession, pk=session_id, learner=learner)
    review_engine.begin_test(session)
    return redirect("review_run", session_id=session.pk)


@login_required
@learner_required
def review_run(request, session_id):
    learner = _learner(request)
    session = get_object_or_404(ReviewSession, pk=session_id, learner=learner)
    if session.finished_at:
        return redirect("review_done", session_id=session.pk)
    if session.phase == ReviewPhase.STUDY:
        return redirect("review_study", session_id=session.pk)

    card = review_engine.current_card(session)
    if card is None:
        review_engine.finish(session)
        return redirect("review_done", session_id=session.pk)

    q = review_engine.make_question(card, session.mode, session.position + 1, session.size)
    return render(request, "core/review_run.html", {
        "session": session, "q": q, "learner": learner,
        "progress": round(session.position / session.size * 100) if session.size else 0,
    })


@login_required
@learner_required
@require_POST
def review_answer(request, session_id):
    learner = _learner(request)
    session = get_object_or_404(ReviewSession, pk=session_id, learner=learner)
    card = review_engine.current_card(session)
    if session.finished_at or card is None:
        return redirect("review_done", session_id=session.pk)

    outcome = review_engine.submit(
        session, card, given=request.POST.get("given", ""),
        elapsed_ms=int(request.POST.get("elapsed_ms") or 0),
    )
    review_engine.advance(session)
    return render(request, "core/partials/review_feedback.html", {
        "outcome": outcome, "session": session,
        "given": request.POST.get("given", ""),
        "is_last": session.position >= session.size,
    })


@login_required
@learner_required
def review_done(request, session_id):
    learner = _learner(request)
    session = get_object_or_404(ReviewSession, pk=session_id, learner=learner)
    if not session.finished_at and session.position >= session.size:
        review_engine.finish(session)
    return render(request, "core/review_done.html", {
        "nav": "memorize", "session": session, "learner": learner,
        "tier_label": review_engine.TIERS.get(session.scope.get("tier"), {}).get("label", "ทุกระดับ"),
        "window_label": review_engine.WINDOWS.get(session.scope.get("window", 0), ""),
        "stats": review_engine.stats(learner),
    })


# ── เรียงความ 书写第二部分 ──────────────────────────────

ESSAY_CONSENT_KEY = "essay_consent"


@login_required
@learner_required
def essay_home(request):
    """หน้าแรกของการเขียน — โจทย์ใหม่ กับงานที่เคยส่ง"""
    learner = _learner(request)
    return render(request, "core/essay_home.html", {
        "nav": "essay", "learner": learner,
        "past": WritingSubmission.objects.filter(learner=learner)
                .select_related("feedback")[:20],
        "consented": bool(request.session.get(ESSAY_CONSENT_KEY)),
        "grader_ready": essay_grader.is_configured(),
    })


@login_required
@learner_required
@require_POST
def essay_consent(request):
    """ยินยอมให้ส่งงานเขียนไปตรวจ — ต้องกดเองก่อนใช้ครั้งแรก"""
    request.session[ESSAY_CONSENT_KEY] = request.POST.get("agree") == "1"
    return redirect("essay_write")


@login_required
@learner_required
def essay_write(request):
    """หน้าเขียน — โจทย์ข้อ 99 สุ่มคำจากคลังของเราเอง ไม่ใช้โจทย์ลิขสิทธิ์"""
    learner = _learner(request)
    words = request.session.get("essay_words")
    if not words:
        pool = VocabItem.objects.filter(hsk_level=5).exclude(hanzi="")[:400]
        words = essay_engine.pick_words(pool)
        request.session["essay_words"] = words

    return render(request, "core/essay_write.html", {
        "nav": "essay", "learner": learner, "words": words,
        "target_chars": essay_engine.TARGET_CHARS,
        "consented": bool(request.session.get(ESSAY_CONSENT_KEY)),
        "grader_ready": essay_grader.is_configured(),
    })


@login_required
@learner_required
@require_POST
def essay_new_words(request):
    request.session.pop("essay_words", None)
    return redirect("essay_write")


@login_required
@learner_required
@require_POST
def essay_submit(request):
    """บันทึกงานเขียนก่อนเสมอ แล้วค่อยเรียกตัวตรวจ

    ลำดับนี้สำคัญ — ถ้าเรียกตัวตรวจก่อนแล้วพัง งานที่ผู้เรียนพิมพ์มาจะหายไปทั้งหมด
    """
    learner = _learner(request)
    text = (request.POST.get("text_zh") or "").strip()
    words = request.session.get("essay_words") or []

    if not text:
        messages.info(request, "ยังไม่ได้เขียนอะไรเลย")
        return redirect("essay_write")

    char_count = essay_engine.count_chars(text)
    submission = WritingSubmission.objects.create(
        learner=learner, task_no=99, required_words=words,
        prompt_zh=" ".join(words), text_zh=text, char_count=char_count,
        minutes_spent=int(request.POST.get("minutes") or 0),
    )
    request.session.pop("essay_words", None)
    return redirect("essay_result", pk=submission.pk)


@login_required
@learner_required
def essay_result(request, pk):
    learner = _learner(request)
    submission = get_object_or_404(WritingSubmission, pk=pk, learner=learner)
    feedback = getattr(submission, "feedback", None)
    return render(request, "core/essay_result.html", {
        "nav": "essay", "learner": learner, "submission": submission,
        "feedback": feedback,
        "consented": bool(request.session.get(ESSAY_CONSENT_KEY)),
        "grader_ready": essay_grader.is_configured(),
    })


@login_required
@learner_required
@require_POST
def essay_grade(request, pk):
    """สั่งตรวจ — ต้องยินยอมก่อน เพราะงานเขียนถูกส่งออกนอกระบบ"""
    learner = _learner(request)
    submission = get_object_or_404(WritingSubmission, pk=pk, learner=learner)

    if not request.session.get(ESSAY_CONSENT_KEY):
        messages.info(request, "ต้องกดยินยอมก่อน เพราะงานเขียนจะถูกส่งไปให้ AI ตรวจ")
        return redirect("essay_result", pk=pk)

    missing = essay_engine.missing_words(submission.text_zh, submission.required_words)
    try:
        observation, usage = essay_grader.observe(
            text_zh=submission.text_zh, task_no=submission.task_no,
            required_words=submission.required_words,
            char_count=submission.char_count, missing=missing,
        )
    except essay_grader.GraderUnavailable as exc:
        messages.info(request, str(exc))
        return redirect("essay_result", pk=pk)

    scores = essay_engine.decide_band(
        char_count=submission.char_count, missing=missing,
        task_no=submission.task_no, observation=observation,
    )
    WritingFeedback.objects.update_or_create(
        submission=submission,
        defaults={
            "scores": scores,
            "total_100": scores["estimated_30"] * 100 // 30,
            "issues": observation.get("issues") or [],
            "graded_by": essay_grader.MODEL,
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
        },
    )
    submission.feedback.scores["observation"] = {
        k: observation.get(k) for k in
        ("suggestions_th", "strengths_th", "next_step_th", "dropped_issues")
    }
    submission.feedback.save(update_fields=["scores", "updated_at"])
    return redirect("essay_result", pk=pk)


@login_required
@learner_required
@require_POST
def essay_dispute(request, pk):
    """ผู้เรียนแย้งว่าจุดที่ AI บอกว่าผิด จริงๆ ไม่ได้ผิด"""
    learner = _learner(request)
    submission = get_object_or_404(WritingSubmission, pk=pk, learner=learner)
    ExplanationNote.objects.create(
        author=request.user, verdict=NoteVerdict.WRONG,
        submission=submission, field_name="essay_issue",
        body=(request.POST.get("body") or "")[:4000],
        source=(request.POST.get("source") or "").strip()[:300],
    )
    messages.info(request, "ส่งคำแย้งแล้ว — เจ้าของระบบจะตรวจให้")
    return redirect("essay_result", pk=submission.pk)


# ── ประวัติรายวัน ──────────────────────────────────────────

@login_required
@learner_required
def history(request):
    """ปฏิทินย้อนหลัง — เลือกวันแล้วเห็นชุดที่ทำวันนั้นทีละข้อ"""
    learner = _learner(request)
    sessions = DrillSession.objects.filter(learner=learner).order_by("-started_at")

    picked = request.GET.get("date")
    session = None
    if picked:
        try:
            day = date.fromisoformat(picked)
        except ValueError:
            day = None
        if day:
            session = sessions.filter(started_at__date=day).first()
    else:
        session = sessions.first()

    answers = []
    if session:
        answers = list(
            session.answers.select_related("card__vocab", "question").order_by("id")
        )

    days = [
        {"date": s.started_at.date(), "answered": s.answered, "correct": s.correct,
         "accuracy": round(s.correct / s.answered * 100) if s.answered else None,
         "finished": s.is_finished}
        for s in sessions[:60]
    ]
    return render(request, "core/history.html", {
        "nav": "history", "days": days, "session": session, "answers": answers,
        "picked": session.started_at.date().isoformat() if session else picked,
        "learner": learner,
    })


# ── คลังคำศัพท์ ────────────────────────────────────────────

SORTS = {
    "priority": ("ตามความสำคัญ", ["frequency_rank", "hanzi"]),
    "exam": ("พบในข้อสอบบ่อยสุด", ["-exam_papers_count", "-exam_occurrences", "hanzi"]),
    "hanzi": ("ตามตัวอักษร", ["hanzi"]),
}


# ตัวเลือกจำนวนแถวต่อหน้า — ไล่ทีละ 5 ตามที่ผู้ใช้เลือกได้เอง
PER_PAGE_CHOICES = [15, 20, 25, 30, 35, 40, 45, 50]
PER_PAGE_DEFAULT = 15


def _per_page(request):
    """อ่านค่าจาก URL แล้วบังคับให้อยู่ในตัวเลือกที่มี — กันคนใส่ ?per=99999 แล้วหน้าค้าง"""
    try:
        value = int(request.GET.get("per") or PER_PAGE_DEFAULT)
    except (TypeError, ValueError):
        return PER_PAGE_DEFAULT
    return value if value in PER_PAGE_CHOICES else PER_PAGE_DEFAULT


def _page(request, queryset, per_page=None):
    """ตัดหน้าแบบรักษาพารามิเตอร์อื่นใน URL ไว้ (ระดับ/การเรียง/แท็บ/คำค้น/จำนวนแถว)"""
    per = per_page or _per_page(request)
    paginator = Paginator(queryset, per)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    params["per"] = per
    return page, params.urlencode()


def _found_filter(request, queryset):
    """กรองตามจำนวนชุดข้อสอบที่พบคำนั้น — เลือกได้หลายค่าพร้อมกัน เช่น ?found=3,4

    เลือกหลายค่าได้เพราะผู้เรียนมักอยากดูเป็นช่วง ("คำที่พบ 3-4 ชุด")
    ไม่ใช่ค่าเดียว และการบังคับให้เลือกทีละค่าทำให้ต้องกดกลับไปกลับมา
    """
    raw = request.GET.get("found") or ""
    values = sorted({
        int(v) for v in raw.split(",")
        if v.strip().isdigit() and 0 <= int(v) <= 9
    })
    if values:
        queryset = queryset.filter(exam_papers_count__in=values)
    return queryset, values


def _found_chips(request, selected):
    """สร้างลิงก์ปุ่มกรอง — กดแล้วสลับเปิด/ปิดค่านั้น โดยเก็บพารามิเตอร์อื่นไว้ครบ"""
    base = request.GET.copy()
    base.pop("page", None)

    chips = []
    for value in range(9, -1, -1):
        toggled = set(selected) ^ {value}
        params = base.copy()
        if toggled:
            params["found"] = ",".join(str(v) for v in sorted(toggled))
        else:
            params.pop("found", None)
        chips.append({"value": value, "on": value in selected, "url": params.urlencode()})

    cleared = base.copy()
    cleared.pop("found", None)
    return chips, cleared.urlencode()


@login_required
def vocab_list(request):
    level = int(request.GET.get("level") or 5)
    sort = request.GET.get("sort") if request.GET.get("sort") in SORTS else "priority"
    query = (request.GET.get("q") or "").strip()
    words = (
        VocabItem.objects.filter(hsk_level=level)
        .exclude(meaning_th="")
        .order_by(*SORTS[sort][1])
    )
    if query:
        # ค้นได้ทั้งตัวอักษรจีน พินอิน และคำแปลไทย — ผู้เรียนจำมาได้แบบไหนก็หาเจอ
        words = words.filter(
            Q(hanzi__icontains=query) | Q(pinyin__icontains=query) | Q(meaning_th__icontains=query)
        )
    words, found_values = _found_filter(request, words)
    found_chips, found_clear_url = _found_chips(request, found_values)
    counts = dict(
        VocabItem.objects.values_list("hsk_level")
        .annotate(n=Count("id")).values_list("hsk_level", "n")
    )
    page, qs = _page(request, words)
    return render(request, "core/vocab_list.html", {
        "nav": "vocab", "page": page, "querystring": qs, "level": level, "sort": sort,
        "query": query, "per_page": _per_page(request), "per_choices": PER_PAGE_CHOICES,
        "found_chips": found_chips, "found_values": found_values, "found_clear_url": found_clear_url,
        "sorts": [(k, v[0]) for k, v in SORTS.items()],
        "levels": [(lv, counts.get(lv, 0)) for lv in range(1, 7)],
    })


# ── เก็งข้อสอบ ─────────────────────────────────────────────

PREDICT_TABS = {
    "must": "คำที่ต้องรู้แน่ๆ",
    "trap": "ตัวลวงประจำ",
    "answer": "คำที่มักเป็นเฉลย",
    "groups": "กลุ่มคำที่ข้อสอบชอบหลอก",
}


@login_required
def predict(request):
    """เก็งข้อสอบจากหลักฐานจริง ไม่ใช่การเดา

    ทุกตัวเลขในหน้านี้นับมาจากข้อสอบเก่า 9 ชุดที่แยกโครงสร้างแล้ว
    ตัดคำสั่งข้อสอบและข้อตัวอย่างออกก่อนนับ
    """
    tab = request.GET.get("tab") if request.GET.get("tab") in PREDICT_TABS else "must"
    # ตัดคำระดับ 1-3 ออกจากหน้านี้ — 是/他/在 โผล่ทุกชุดจริงแต่ไม่ใช่สิ่งที่ต้องเก็ง
    base = VocabItem.objects.filter(hsk_level__gte=4).exclude(meaning_th="")

    groups = None
    if tab == "must":
        items = base.filter(exam_papers_count__gte=1).order_by(
            "-exam_papers_count", "-exam_occurrences", "hanzi")
    elif tab == "trap":
        items = base.filter(exam_as_distractor__gte=1).order_by(
            "-exam_as_distractor", "-exam_papers_count", "hanzi")
    elif tab == "answer":
        items = base.filter(exam_as_answer__gte=1).order_by(
            "-exam_as_answer", "-exam_papers_count", "hanzi")
    else:
        items = SynonymGroup.objects.prefetch_related("items").order_by("name")
        groups = True

    found_chips = found_values = None
    found_clear_url = ""
    if not groups:
        items, found_values = _found_filter(request, items)
        found_chips, found_clear_url = _found_chips(request, found_values)

    page, qs = _page(request, items)
    return render(request, "core/predict.html", {
        "nav": "predict", "tab": tab, "tabs": PREDICT_TABS.items(),
        "page": page, "querystring": qs, "is_groups": groups,
        "per_page": _per_page(request), "per_choices": PER_PAGE_CHOICES,
        "found_chips": found_chips, "found_values": found_values, "found_clear_url": found_clear_url,
        "total_words": base.filter(exam_papers_count__gte=1).count(),
        "never_seen": base.filter(exam_papers_count=0).count(),
    })


# ── สถิติ ─────────────────────────────────────────────────

@login_required
@learner_required
def stats(request):
    learner = _learner(request)
    sessions = DrillSession.objects.filter(learner=learner).order_by("-started_at")[:14]
    answered = sum(s.answered for s in sessions)
    correct = sum(s.correct for s in sessions)
    causes = (
        ErrorLog.objects.filter(learner=learner)
        .values("code").annotate(n=Count("id")).order_by("-n")[:6]
    )
    labels = dict(ErrorCode.choices)
    return render(request, "core/stats.html", {
        "nav": "stats", "learner": learner, "sessions": sessions,
        "accuracy": round(correct / answered * 100) if answered else None,
        "answered": answered,
        "causes": [{"label": labels.get(c["code"], c["code"]), "n": c["n"],
                    "advice": ErrorCode.advice(c["code"])} for c in causes],
        "cards_total": Card.objects.filter(learner=learner).count(),
        "due_now": srs.due_queryset(learner).count(),
        "summary": selection.today_summary(learner),
        "mock": mock_engine.stats(learner),
    })


# ── ที่มาข้อมูล ────────────────────────────────────────────

@login_required
def docs(request):
    """หน้าอธิบายว่าข้อมูลทุกอย่างมาจากไหน และเก็งข้อสอบด้วยหลักอะไร

    ตัวเลขบนหน้านี้ดึงสดจากฐานข้อมูล ไม่ได้พิมพ์แช่ไว้ — ถ้าข้อมูลเปลี่ยน หน้านี้เปลี่ยนตาม
    """
    from .models import Question, QuestionStatus, SynonymGroup

    return render(request, "core/docs.html", {
        "nav": "docs",
        "counts": {
            "vocab": VocabItem.objects.count(),
            "vocab_with_exam": VocabItem.objects.filter(exam_papers_count__gte=1).count(),
            # SQLite ค้นใน JSON ไม่ได้ — นับฝั่ง Python (แค่ 2 พันแถว ไม่หนัก)
            "vocab_flagged": sum(
                1 for tags in VocabItem.objects.values_list("tags", flat=True)
                if "needs_review" in (tags or [])
            ),
            "questions_active": Question.objects.filter(status=QuestionStatus.ACTIVE).count(),
            "questions_draft": Question.objects.filter(status=QuestionStatus.DRAFT).count(),
            "groups": SynonymGroup.objects.count(),
        },
    })


# ── คำเชื่อมและการจับคู่คำ ─────────────────────────────────

GRAMMAR_TABS = {
    "conn": "คำเชื่อมประโยค",
    "match": "การจับคู่คำ",
}

POS_FILTERS = [("", "ทุกชนิด"), ("v", "กริยา"), ("n", "คำนาม"), ("adj", "คำคุณศัพท์"), ("adv", "คำวิเศษณ์")]


@login_required
def grammar(request):
    """คำเชื่อม + การจับคู่คำ — สองอย่างที่ท่องเป็นคำเดี่ยวแล้วใช้ไม่ได้

    คำเชื่อมต้องจำเป็นรูปประโยค (尽管…还是…) ส่วนกริยาต้องจำว่าคู่กับคำนามตัวไหน
    (采取措施 ไม่ใช่ 采取方法) — ข้อสอบ 选词填空 ถามสองอย่างนี้เป็นหลัก
    """
    tab = request.GET.get("tab") if request.GET.get("tab") in GRAMMAR_TABS else "conn"

    context = {
        "nav": "grammar", "tab": tab, "tabs": GRAMMAR_TABS.items(),
    }

    if tab == "conn":
        context["groups"] = grammar_engine.connective_groups()
        context["uncovered"] = grammar_engine.uncovered_connectives()
    else:
        query = (request.GET.get("q") or "").strip()
        pos = request.GET.get("pos") or ""
        pos = pos if pos in dict(POS_FILTERS) else ""
        try:
            min_level = int(request.GET.get("min_level") or 4)
        except ValueError:
            min_level = 4
        min_level = min_level if min_level in (1, 4, 5) else 4
        items = grammar_engine.collocation_queryset(query, pos, min_level)
        page, qs = _page(request, items)
        context.update({
            "page": page, "querystring": qs, "query": query, "pos": pos,
            "pos_filters": POS_FILTERS, "min_level": min_level,
            "level_filters": [(4, "HSK4 ขึ้นไป"), (5, "HSK5 เท่านั้น"), (1, "ทุกระดับ")],
            "per_page": _per_page(request), "per_choices": PER_PAGE_CHOICES,
        })

    return render(request, "core/grammar.html", context)


# ── โปรไฟล์ผู้ใช้ ───────────────────────────────────────────

@login_required
def profile(request):
    """หน้าโปรไฟล์ของคนที่ล็อกอินอยู่ — ดูอย่างเดียว ยังแก้ไขไม่ได้

    ตัวเลขทั้งหมดดึงสดจากฐานข้อมูล ไม่ได้เก็บซ้ำไว้ที่ไหน
    """
    learner = _learner(request)
    context = {"nav": "profile", "learner": learner}

    if learner:
        sessions = DrillSession.objects.filter(learner=learner)
        answered = sum(s.answered for s in sessions)
        correct = sum(s.correct for s in sessions)
        context.update({
            "placement": learner.placement_tests.filter(finished_at__isnull=False).first(),
            "days_to_exam": srs.days_to_exam(learner),
            "in_freeze": srs.in_freeze(learner),
            "cards_total": Card.objects.filter(learner=learner).count(),
            "sessions_total": sessions.count(),
            "days_practiced": sessions.filter(finished_at__isnull=False).count(),
            "answered": answered,
            "accuracy": round(correct / answered * 100) if answered else None,
            "coaches": learner.coaches.all(),
            "mock": mock_engine.stats(learner),
        })
    return render(request, "core/profile.html", context)


# ── ความคืบหน้าของกลุ่ม ────────────────────────────────────

@login_required
def group_progress(request):
    """ทุกคนเห็นได้ — แต่เห็นเฉพาะ 'ความพยายาม' ไม่เห็นความแม่นของคนอื่น"""
    rows = progress_engine.group_progress()
    return render(request, "core/group_progress.html", {
        "nav": "progress", "rows": rows,
        "not_done": [r for r in rows if not r["done_today"]],
    })


# ── จัดการผู้ใช้ (เฉพาะ admin) ─────────────────────────────

def _is_admin(user) -> bool:
    return user.is_superuser or user.role == Role.ADMIN


@login_required
def user_admin(request):
    """admin เพิ่มผู้ใช้ได้อย่างเดียว — แก้หรือลบต้องไปที่หน้าจัดการข้อมูล

    จำกัดอำนาจไว้แค่นี้โดยตั้งใจ การลบผู้ใช้ลบประวัติการฝึกทั้งหมดไปด้วย
    จึงไม่ควรทำได้จากหน้าเว็บธรรมดา
    """
    if not _is_admin(request.user):
        return render(request, "core/forbidden.html", {"nav": ""}, status=403)

    error = None
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        display_name = (request.POST.get("display_name") or "").strip()
        password = request.POST.get("password") or ""
        exam_date_raw = request.POST.get("exam_date") or ""
        backup_raw = request.POST.get("backup_exam_date") or ""

        if not username or not password or not exam_date_raw:
            error = "ต้องกรอกชื่อผู้ใช้ รหัสผ่าน และวันสอบให้ครบ"
        elif len(password) < 8:
            error = "รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร"
        else:
            try:
                profile, cards = create_learner(
                    username=username, password=password, display_name=display_name,
                    exam_date=date.fromisoformat(exam_date_raw),
                    backup_exam_date=date.fromisoformat(backup_raw) if backup_raw else None,
                    coach=request.user if _is_admin(request.user) else None,
                )
                messages.info(
                    request,
                    f"เพิ่มผู้เรียน {profile.user.username} แล้ว · สร้างการ์ดทบทวน {cards} ใบ · "
                    f"บอกรหัสผ่านให้เจ้าตัวด้วย ระบบไม่ได้ส่งให้อัตโนมัติ",
                )
                return redirect("user_admin")
            except ValueError as exc:
                error = str(exc)
            except Exception:
                error = "วันที่ไม่ถูกต้อง ใช้รูปแบบ ปี-เดือน-วัน"

    return render(request, "core/user_admin.html", {
        "nav": "users", "error": error,
        "users": User.objects.select_related("learner_profile").order_by("-date_joined"),
        "form": request.POST if request.method == "POST" else {},
    })


# ── พาร์ทเขียน: เรียงคำ ────────────────────────────────────

WORDORDER_SEEN_KEY = "wordorder_seen"


@login_required
@learner_required
def word_order(request):
    """ฝึกเรียงคำทีละข้อ — พาร์ทที่ทำคะแนนได้ง่ายที่สุดในข้อสอบ

    แยกจากชุดฝึกรายวันเพราะหน้าจอคนละแบบ (ลากคำ ไม่ใช่เลือก ก-ง)
    แต่ข้อที่ผิดยังไหลเข้า ErrorLog เหมือนกัน จึงกลับมาถามในชุดวันถัดไปได้
    """
    learner = _learner(request)
    seen = request.session.get(WORDORDER_SEEN_KEY, [])
    result = question = None

    if request.method == "POST":
        question = get_object_or_404(Question, pk=request.POST.get("question_id"))
        result = writing_engine.check(question, request.POST.get("given", ""))
        if learner:
            writing_engine.record_result(learner, question, result)
        if question.pk not in seen:
            seen.append(question.pk)
            request.session[WORDORDER_SEEN_KEY] = seen[-60:]
    else:
        question = writing_engine.pick_question(exclude_ids=seen)

    return render(request, "core/word_order.html", {
        "nav": "writing", "question": question, "result": result,
        "key_vocab": reading_engine.key_vocab(question) if question else [],
        "words": writing_engine.words_of(question) if question else [],
        "done_count": len(seen),
        "total": Question.objects.filter(qtype="word_order", status="active").count(),
    })


# ── ให้คนตรวจคำอธิบายของ AI ────────────────────────────────

@login_required
@require_POST
def explanation_note(request, question_id):
    """รับสิ่งที่ผู้ใช้ตรวจมาได้ — เก็บไว้ ไม่ใช่แค่รับแจ้งแล้วทิ้ง

    ถ้าผู้ใช้พิมพ์คำอธิบายที่ถูกมาด้วย จะถูกเก็บไว้รอเจ้าของระบบกดรับ
    แล้วแสดงแทนของ AI — ทำให้คำอธิบายค่อยๆ ถูกแทนที่ด้วยของที่คนยืนยันแล้ว
    """
    question = get_object_or_404(Question, pk=question_id)
    verdict = request.POST.get("verdict")
    if verdict not in dict(NoteVerdict.choices):
        verdict = NoteVerdict.WRONG

    body = (request.POST.get("body") or "").strip()
    if verdict == NoteVerdict.WRONG and body:
        verdict = NoteVerdict.CORRECTED

    note = ExplanationNote.objects.create(
        question=question, author=request.user, verdict=verdict,
        body=body[:4000], source=(request.POST.get("source") or "").strip()[:300],
    )

    # ทำเครื่องหมายว่าคำอธิบายนี้ถูกโต้แย้ง เพื่อให้คนอื่นเห็นก่อนเชื่อ
    if verdict in (NoteVerdict.WRONG, NoteVerdict.CORRECTED):
        explanation = dict(question.explanation or {})
        explanation["disputed"] = True
        question.explanation = explanation
        question.save(update_fields=["explanation", "updated_at"])

    return render(request, "core/partials/note_thanks.html", {"note": note})


@login_required
@require_POST
def vocab_note(request, vocab_id):
    """แย้งคำแปลศัพท์ — คำแปลไทยทั้ง 2,206 คำมาจาก AI เหมือนกัน จึงต้องแย้งได้เหมือนกัน

    ใช้ตารางเดียวกับการแย้งคำอธิบายเฉลย เพื่อให้เจ้าของระบบมีที่ตรวจที่เดียว
    """
    vocab = get_object_or_404(VocabItem, pk=vocab_id)
    verdict = request.POST.get("verdict")
    if verdict not in dict(NoteVerdict.choices):
        verdict = NoteVerdict.WRONG

    body = (request.POST.get("body") or "").strip()
    if verdict == NoteVerdict.WRONG and body:
        verdict = NoteVerdict.CORRECTED

    note = ExplanationNote.objects.create(
        vocab=vocab, author=request.user, verdict=verdict,
        body=body[:4000], source=(request.POST.get("source") or "").strip()[:300],
    )

    if verdict in (NoteVerdict.WRONG, NoteVerdict.CORRECTED):
        tags = list(vocab.tags or [])
        if "disputed" not in tags:
            tags.append("disputed")
            vocab.tags = tags
            vocab.save(update_fields=["tags", "updated_at"])

    return render(request, "core/partials/note_thanks.html", {"note": note})


@login_required
def explanation_review(request):
    """รายการที่คนส่งมาตรวจ — เจ้าของระบบกดรับหรือไม่รับ"""
    if not _is_admin(request.user):
        return render(request, "core/forbidden.html", {"nav": ""}, status=403)

    if request.method == "POST":
        note = get_object_or_404(ExplanationNote, pk=request.POST.get("note_id"))
        action = request.POST.get("action")
        if action == "accept" and note.body:
            note.status = NoteStatus.ACCEPTED
            if note.question_id:
                explanation = dict(note.question.explanation or {})
                explanation["disputed"] = False
                explanation["human_verified"] = True
                note.question.explanation = explanation
                note.question.save(update_fields=["explanation", "updated_at"])
            elif note.vocab_id:
                # คำแปลที่คนยืนยันแล้วมาแทนของ AI จริงๆ ไม่ใช่แค่ทำเครื่องหมาย
                vocab = note.vocab
                vocab.meaning_th = note.body[:255]
                tags = [t for t in (vocab.tags or []) if t not in ("disputed", "needs_review")]
                if "human_verified" not in tags:
                    tags.append("human_verified")
                vocab.tags = tags
                vocab.save(update_fields=["meaning_th", "tags", "updated_at"])
            messages.info(request, f"รับคำอธิบายจาก {note.author} มาใช้แล้ว")
        elif action == "reject":
            note.status = NoteStatus.REJECTED
            messages.info(request, "ทำเครื่องหมายว่าไม่รับแล้ว")
        note.save(update_fields=["status", "updated_at"])
        return redirect("explanation_review")

    return render(request, "core/explanation_review.html", {
        "nav": "review",
        "open_notes": ExplanationNote.objects.filter(status=NoteStatus.OPEN)
            .select_related("question", "vocab", "author"),
        "handled": ExplanationNote.objects.exclude(status=NoteStatus.OPEN)
            .select_related("question", "vocab", "author")[:30],
    })


# ── ข้อสอบจำลอง ────────────────────────────────────────────

@login_required
def mock_home(request):
    """หน้าแรกของการสอบจำลอง — สถิติที่ผ่านมา + ปุ่มเริ่ม"""
    learner = _learner(request)
    if not learner:
        return render(request, "core/no_profile.html", {"nav": "mock"})

    running = MockExam.objects.filter(
        learner=learner, started_at__isnull=False, finished_at__isnull=True,
    ).order_by("-started_at").first()

    return render(request, "core/mock_home.html", {
        "nav": "mock", "stats": mock_engine.stats(learner), "running": running,
        "blueprint": mock_engine.READING_BLUEPRINT,
        "minutes": mock_engine.READING_MINUTES,
    })


@login_required
@learner_required
def mock_start(request):
    learner = _learner(request)
    exam = mock_engine.start(learner)
    if exam is None:
        messages.info(
            request,
            "ยังสร้างชุดจำลองไม่ได้ — คลังข้อสอบพาร์ทอ่านมีไม่พอ "
            "ให้เจ้าของระบบรัน bootstrap ใส่ข้อสอบก่อน",
        )
        return redirect("mock_home")
    return redirect("mock_run", exam_id=exam.pk)


@login_required
@learner_required
def mock_run(request, exam_id):
    """หน้าทำข้อสอบ — ซ่อนเมนู จับเวลา ไม่เฉลยระหว่างทาง"""
    learner = _learner(request)
    exam = get_object_or_404(MockExam, pk=exam_id, learner=learner)
    if exam.finished_at:
        return redirect("mock_result", exam_id=exam.pk)
    if exam.is_expired:
        mock_engine.grade(exam, auto=True)
        messages.info(request, "หมดเวลาแล้ว ระบบส่งคำตอบให้อัตโนมัติ")
        return redirect("mock_result", exam_id=exam.pk)

    try:
        index = max(1, min(int(request.GET.get("q") or 1), exam.question_count))
    except ValueError:
        index = 1

    if not exam.queue:
        messages.info(request, "ชุดข้อสอบนี้ว่างเปล่า — คลังข้อสอบอาจยังไม่ได้ใส่ข้อมูล")
        return redirect("mock_home")

    qid = exam.queue[index - 1]
    question = Question.objects.filter(pk=qid).prefetch_related("options").select_related("group").first()

    return render(request, "core/mock_run.html", {
        "exam": exam, "question": question, "index": index,
        # ใช้ตัวแปรชื่อ q เหมือนหน้าชุดฝึก เพื่อให้ partial เดียวกันใช้ได้ทั้งสองที่
        "q": reading_engine.build(question) if question else None,
        "options": list(question.options.all().order_by("order", "id")) if question else [],
        "given": (exam.answers or {}).get(str(qid), ""),
        "is_flagged": qid in (exam.flagged or []),
        "states": mock_engine.question_states(exam),
        "seconds_left": exam.seconds_left,
        "focus_mode": True,
    })


@login_required
@learner_required
@require_POST
def mock_answer(request, exam_id):
    learner = _learner(request)
    exam = get_object_or_404(MockExam, pk=exam_id, learner=learner)
    if exam.finished_at:
        return redirect("mock_result", exam_id=exam.pk)

    qid = int(request.POST.get("question_id"))
    if request.POST.get("action") == "flag":
        mock_engine.toggle_flag(exam, qid)
    else:
        mock_engine.save_answer(exam, qid, request.POST.get("given", ""))

    index = int(request.POST.get("index") or 1)
    if request.POST.get("next") == "1":
        index = min(index + 1, exam.question_count)
    elif request.POST.get("prev") == "1":
        index = max(index - 1, 1)
    return redirect(f"{reverse('mock_run', args=[exam.pk])}?q={index}")


@login_required
@learner_required
def mock_submit(request, exam_id):
    """หน้ายืนยันก่อนส่ง — บอกจำนวนข้อที่ยังไม่ตอบและที่ปักธงไว้"""
    learner = _learner(request)
    exam = get_object_or_404(MockExam, pk=exam_id, learner=learner)
    if exam.finished_at:
        return redirect("mock_result", exam_id=exam.pk)

    if request.method == "POST":
        mock_engine.grade(exam, auto=exam.is_expired)
        return redirect("mock_result", exam_id=exam.pk)

    states = mock_engine.question_states(exam)
    return render(request, "core/mock_submit.html", {
        "exam": exam, "states": states,
        "unanswered": [s for s in states if not s["answered"]],
        "flagged": [s for s in states if s["flagged"]],
        "seconds_left": exam.seconds_left,
        "focus_mode": True,
    })


@login_required
@learner_required
def mock_result(request, exam_id):
    """ผลสอบ — ขึ้นต้นด้วยสิ่งที่ต้องแก้ ไม่ใช่คะแนน"""
    learner = _learner(request)
    exam = get_object_or_404(MockExam, pk=exam_id, learner=learner)
    if not exam.finished_at:
        return redirect("mock_run", exam_id=exam.pk)

    answers = exam.answers or {}
    questions = {
        q.pk: q for q in Question.objects.filter(pk__in=exam.queue or [])
        .prefetch_related("options").select_related("group")
    }
    review = []
    for i, qid in enumerate(exam.queue or [], start=1):
        question = questions.get(qid)
        if not question:
            continue
        options = list(question.options.all().order_by("order", "id"))
        right = next((o.text for o in options if o.is_correct), question.answer_text)
        given = (answers.get(str(qid)) or "").strip()
        review.append({
            "number": i, "question": question, "options": options,
            "given": given, "right": right,
            "is_correct": bool(given) and given == (right or "").strip(),
            "skipped": not given,
            "distractors": [o for o in options if not o.is_correct and o.rationale_th],
        })

    wrong = [r for r in review if not r["is_correct"]]
    causes = {}
    for r in wrong:
        code = (r["question"].explanation or {}).get("error_code") or ""
        if code:
            causes[code] = causes.get(code, 0) + 1
    labels = dict(ErrorCode.choices)

    return render(request, "core/mock_result.html", {
        "nav": "mock", "exam": exam, "review": review, "wrong": wrong,
        "stats": mock_engine.stats(learner),
        "causes": sorted(
            ({"label": labels.get(c, c), "n": n, "advice": ErrorCode.advice(c)}
             for c, n in causes.items()),
            key=lambda x: -x["n"],
        )[:4],
    })
