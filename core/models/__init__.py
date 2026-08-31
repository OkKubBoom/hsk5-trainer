"""Data model ทั้งหมดของ HSK5 Trainer

แบ่งเป็นหกโมดูลตามหน้าที่ แต่ import ออกมาที่นี่ให้ใช้ได้แบบ `from core.models import X`

  base         ค่าคงที่ + abstract (Provenance, TimeStamped, ErrorCode)
  users        User, LearnerProfile, LoginDay
  lexicon      ExamSpec, VocabItem, SynonymGroup, GrammarPoint, WritingTemplate
  srs          Card, ReviewLog
  content      AudioClip, ItemGroup, Question, QuestionOption
  practice     DrillSession, AnswerRecord, DailyRecord, MockExam, ReviewSession,
               DictationAttempt, WritingSubmission, WritingFeedback
  diagnostics  ErrorLog
  placement    PlacementTest, PlacementAnswer
  feedback     ExplanationNote — คนตรวจคำอธิบายของ AI
"""
from .base import ErrorCode, Provenance, Section, SourceType, Standard, TimeStamped
from .users import LearnerProfile, LoginDay, Role, User
from .lexicon import ExamSpec, GrammarPoint, SynonymGroup, VocabItem, WritingTemplate
from .srs import Card, CardState, CardType, Rating, ReviewLog
from .content import (
    AudioClip, DistractorType, GroupKind, ItemGroup,
    Question, QuestionOption, QuestionStatus, QuestionType,
)
from .practice import (
    AnswerRecord, DailyRecord, DictationAttempt, DrillSession,
    MockExam, ReviewMode, ReviewPhase, ReviewSession, WritingFeedback, WritingSubmission,
)
from .diagnostics import ErrorLog
from .placement import PlacementAnswer, PlacementTest
from .feedback import ExplanationNote, NoteStatus, NoteVerdict

__all__ = [
    "ErrorCode", "Provenance", "Section", "SourceType", "Standard", "TimeStamped",
    "User", "Role", "LearnerProfile", "LoginDay",
    "ExamSpec", "VocabItem", "SynonymGroup", "GrammarPoint", "WritingTemplate",
    "Card", "CardType", "CardState", "ReviewLog", "Rating",
    "AudioClip", "ItemGroup", "GroupKind", "Question", "QuestionType",
    "QuestionStatus", "QuestionOption", "DistractorType",
    "DrillSession", "AnswerRecord", "DailyRecord", "MockExam",
    "ReviewSession", "ReviewMode", "ReviewPhase",
    "DictationAttempt", "WritingSubmission", "WritingFeedback",
    "ErrorLog",
    "PlacementTest", "PlacementAnswer",
    "ExplanationNote", "NoteVerdict", "NoteStatus",
]
