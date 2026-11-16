"""
What a quiz looks like — stored as JSON in messages.content of a message
with content_type = "quiz".

The LLM produces this structure (step 2), the backend validates it here
before it is saved, and the frontend draws it. The same models check the
LLM output, so a broken or incomplete quiz never reaches the student.

    {
      "version": 1,
      "scope": "course",               # "chat" (current chat) or "course"
      "topic": "PtL-Anlagen",          # optional, what the student asked for
      "language": "de",
      "questions": [
        {
          "type": "single_choice",
          "question": "Welche Anlage ...?",
          "options": ["...", "...", "...", "..."],
          "correct": [1],              # indexes into options
          "explanation": "Green Fuels Lausitz ... 200.000 t/a ...",
          "source": "[PtL_Anlagen....pdf](http://.../file.pdf#page=2)",
          "page": 2
        }
      ]
    }

"correct" is a list on purpose: single choice has exactly one index,
later question types (multiple choice) can have several without a change
of the format. Other later types (gap text, free text) add their own
fields; "type" tells the frontend how to draw a question.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

QUIZ_FORMAT_VERSION = 1

# Number of questions the student can choose (default 5).
QUESTION_COUNTS = (3, 5, 10, 20)
DEFAULT_QUESTION_COUNT = 5

QuizScope = Literal["chat", "course"]


class QuizQuestion(BaseModel):
    type: Literal["single_choice"] = "single_choice"
    question: str = Field(min_length=5, max_length=600)
    options: list[str] = Field(min_length=2, max_length=6)
    correct: list[int] = Field(min_length=1)
    explanation: str = Field(default="", max_length=1500)
    # Citation as the chat answers have it: a markdown link to the file,
    # copied from the context label (never invented by the model).
    source: str = Field(default="", max_length=1000)
    page: int | None = None

    @field_validator("question", "explanation", "source")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("options")
    @classmethod
    def _options(cls, options: list[str]) -> list[str]:
        options = [o.strip() for o in options]
        if any(not o for o in options):
            raise ValueError("empty answer option")
        if len({o.casefold() for o in options}) != len(options):
            raise ValueError("duplicate answer options")
        return options

    @model_validator(mode="after")
    def _check_correct(self):
        if len(set(self.correct)) != len(self.correct):
            raise ValueError("duplicate index in 'correct'")
        if any(i < 0 or i >= len(self.options) for i in self.correct):
            raise ValueError("'correct' points to an option that does not exist")
        if self.type == "single_choice" and len(self.correct) != 1:
            raise ValueError("single_choice needs exactly one correct option")
        return self


class Quiz(BaseModel):
    version: int = QUIZ_FORMAT_VERSION
    scope: QuizScope = "course"
    topic: str | None = None
    language: str = "en"
    questions: list[QuizQuestion] = Field(min_length=1, max_length=max(QUESTION_COUNTS))

    @model_validator(mode="after")
    def _no_duplicate_questions(self):
        seen = set()
        for q in self.questions:
            key = " ".join(q.question.casefold().split())
            if key in seen:
                raise ValueError(f"duplicate question: {q.question[:60]}")
            seen.add(key)
        return self

    def to_json(self) -> str:
        """What is stored in messages.content."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, text: str) -> "Quiz":
        return cls.model_validate_json(text)


def check_answer(question: QuizQuestion, answer: list[int]) -> bool:
    """Is the student's answer right? (Order does not matter.)"""
    return sorted(set(answer)) == sorted(question.correct)
