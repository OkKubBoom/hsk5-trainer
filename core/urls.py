from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", auth_views.LoginView.as_view(template_name="core/login.html",
                                                redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),

    path("placement/", views.placement_start, name="placement_start"),
    path("placement/<int:test_id>/", views.placement_run, name="placement_run"),
    path("placement/<int:test_id>/answer/", views.placement_answer, name="placement_answer"),
    path("placement/<int:test_id>/result/", views.placement_result, name="placement_result"),

    path("drill/", views.drill_start, name="drill_start"),
    path("drill/run/", views.drill_run, name="drill_run"),
    path("drill/answer/", views.drill_answer, name="drill_answer"),
    path("drill/<int:session_id>/done/", views.drill_done, name="drill_done"),

    path("history/", views.history, name="history"),
    path("vocab/", views.vocab_list, name="vocab_list"),
    path("predict/", views.predict, name="predict"),
    path("grammar/", views.grammar, name="grammar"),
    path("writing/", views.word_order, name="word_order"),
    path("mock/", views.mock_home, name="mock_home"),
    path("mock/start/", views.mock_start, name="mock_start"),
    path("mock/<int:exam_id>/", views.mock_run, name="mock_run"),
    path("mock/<int:exam_id>/answer/", views.mock_answer, name="mock_answer"),
    path("mock/<int:exam_id>/submit/", views.mock_submit, name="mock_submit"),
    path("mock/<int:exam_id>/result/", views.mock_result, name="mock_result"),
    path("stats/", views.stats, name="stats"),
    path("docs/", views.docs, name="docs"),
    path("profile/", views.profile, name="profile"),
    path("progress/", views.group_progress, name="group_progress"),
    path("users/", views.user_admin, name="user_admin"),
    path("explanation/<int:question_id>/note/", views.explanation_note, name="explanation_note"),
    path("vocab/<int:vocab_id>/note/", views.vocab_note, name="vocab_note"),
    path("explanation/review/", views.explanation_review, name="explanation_review"),
]
