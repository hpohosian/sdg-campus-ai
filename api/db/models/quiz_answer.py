from sqlalchemy import BigInteger, Column, Integer, String, UniqueConstraint

from db.base import Base


class QuizAnswerModel(Base):
    """
    One answer of the student to one question of a quiz.

    The quiz itself is a chat message (messages.content_type = "quiz",
    the questions as JSON in messages.content). This table stores what the
    student chose, so the quiz card can be restored after a reload and the
    result shown at the end. Quizzes are for self-study only: nobody else
    (no teacher) sees these answers.

    One answer per question: answering again is not possible. "Retry
    mistakes" creates a NEW quiz message with those questions.
    """
    __tablename__ = "quiz_answers"

    id = Column(Integer, primary_key=True)

    message_id = Column(Integer, nullable=False, index=True)  # the quiz message
    question_index = Column(Integer, nullable=False)           # 0-based
    # The student's choice. A list as JSON text ("[2]") so later question
    # types (multiple choice: "[0, 3]", gap text, free text) fit as well.
    answer = Column(String(2000), nullable=False)
    is_correct = Column(Integer, nullable=False)                # 0/1

    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "question_index", name="uq_quiz_answer_question"),
    )
