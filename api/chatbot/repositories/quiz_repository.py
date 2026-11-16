import json
import time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from db.models.quiz_answer import QuizAnswerModel


class QuizRepository:
    """Answers of the student to quiz questions (see db/models/quiz_answer.py)."""

    def __init__(self, db: DBSession):
        self.db = db

    def save_answer(self, message_id: int, question_index: int, answer: list[int], is_correct: bool):
        """
        Stores one answer. Returns the stored row, or the EXISTING row if
        this question was already answered (a question is answered once:
        a double click or a second tab must not overwrite the first answer).
        """
        row = QuizAnswerModel(
            message_id=message_id,
            question_index=question_index,
            answer=json.dumps(answer),
            is_correct=1 if is_correct else 0,
            created_at=int(time.time()),
        )
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return self.get_answer(message_id, question_index)
        self.db.refresh(row)
        return row

    def get_answer(self, message_id: int, question_index: int):
        return self.db.execute(
            select(QuizAnswerModel).where(
                QuizAnswerModel.message_id == message_id,
                QuizAnswerModel.question_index == question_index,
            )
        ).scalar_one_or_none()

    def get_answers(self, message_ids: list[int]) -> dict[int, list[QuizAnswerModel]]:
        """{message_id: [answers, by question_index]} for several quiz messages at once."""
        out: dict[int, list[QuizAnswerModel]] = {}
        if not message_ids:
            return out
        rows = self.db.execute(
            select(QuizAnswerModel)
            .where(QuizAnswerModel.message_id.in_(message_ids))
            .order_by(QuizAnswerModel.message_id, QuizAnswerModel.question_index)
        ).scalars()
        for row in rows:
            out.setdefault(row.message_id, []).append(row)
        return out
