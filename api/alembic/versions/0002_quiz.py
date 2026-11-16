"""quizzes

messages.content_type ("text" | "quiz") and the quiz_answers table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default fills the column for all existing messages.
    op.add_column('messages', sa.Column(
        'content_type', sa.String(length=16), nullable=False, server_default='text'
    ))
    op.create_table('quiz_answers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('message_id', sa.Integer(), nullable=False),
    sa.Column('question_index', sa.Integer(), nullable=False),
    sa.Column('answer', sa.String(length=2000), nullable=False),
    sa.Column('is_correct', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('message_id', 'question_index', name='uq_quiz_answer_question')
    )
    op.create_index(op.f('ix_quiz_answers_message_id'), 'quiz_answers', ['message_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_quiz_answers_message_id'), table_name='quiz_answers')
    op.drop_table('quiz_answers')
    op.drop_column('messages', 'content_type')
