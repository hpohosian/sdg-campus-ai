from sqlalchemy.orm import Session as DBSession
from sqlalchemy import select
from db.models.message import MessageModel
import time


class MessageRepository:
    def __init__(self, db: DBSession):
        self.db = db

    def get(self, message_id: int):
        result = self.db.execute(
            select(MessageModel).where(MessageModel.id == message_id)
        )
        return result.scalar_one_or_none()

    def get_by_session(self, session_id: str):
        """
        ALL rows for a session (every version of every message), ordered
        by created_at. Mostly useful for admin/debug purposes -- for the
        conversation the user is actually seeing, use get_active_thread().
        """
        result = self.db.execute(
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.created_at.asc())
        )
        return result.scalars().all()

    # =========================
    # ACTIVE CONVERSATION THREAD
    # =========================
    def get_active_thread(self, session_id: str):
        """
        Walks the message tree starting at the active root and following
        each node's active child. This is "the conversation" as the user
        currently sees it.

        Every message has a parent_id (None for the first message of the
        session) and an is_active flag that's meaningful only relative to
        its siblings (other rows sharing the same parent_id). Editing or
        regenerating never deletes anything -- it adds a new sibling and
        flips is_active -- so returning to an older version is just
        flipping the flag back, and this walk picks it up automatically.
        """
        root = self.db.execute(
            select(MessageModel).where(
                MessageModel.session_id == session_id,
                MessageModel.parent_id.is_(None),
                MessageModel.is_active == 1,
            )
        ).scalar_one_or_none()

        thread = []
        current = root
        while current is not None:
            thread.append(current)
            current = self.db.execute(
                select(MessageModel).where(
                    MessageModel.parent_id == current.id,
                    MessageModel.is_active == 1,
                )
            ).scalar_one_or_none()

        return thread

    def get_siblings(self, session_id: str, parent_id: int | None):
        """All versions sharing the same parent_id (the same "slot" in the
        conversation), oldest -> newest."""
        stmt = select(MessageModel).where(MessageModel.session_id == session_id)
        if parent_id is None:
            stmt = stmt.where(MessageModel.parent_id.is_(None))
        else:
            stmt = stmt.where(MessageModel.parent_id == parent_id)
        stmt = stmt.order_by(MessageModel.created_at.asc())
        return self.db.execute(stmt).scalars().all()

    def create(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens_used: int | None = None,
        image_path: str | None = None,
        parent_id: int | None = None,
        is_active: bool = True,
    ):
        message = MessageModel(
            session_id=session_id,
            role=role,
            content=content,
            created_at=int(time.time()),
            tokens_used=tokens_used,
            image_path=image_path,
            parent_id=parent_id,
            is_active=1 if is_active else 0,
        )

        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        return message

    # =========================
    # VERSIONING
    # =========================
    def activate(self, message_id: int):
        """Makes `message_id` the active sibling under its parent and
        deactivates every other sibling in that same slot."""
        target = self.get(message_id)
        if not target:
            return None

        siblings = self.get_siblings(target.session_id, target.parent_id)
        for sib in siblings:
            sib.is_active = 1 if sib.id == target.id else 0
            self.db.add(sib)

        self.db.commit()
        self.db.refresh(target)
        return target
    