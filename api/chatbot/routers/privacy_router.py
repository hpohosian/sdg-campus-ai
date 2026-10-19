"""
Privacy (GDPR) and data-retention endpoints.

Called ONLY by the Moodle plugin's Privacy API provider and its daily cleanup
task -- never by students. On top of the HMAC signature (middleware/auth.py)
every endpoint needs the shared X-Internal-Api-Key, like /rag/index.

The data subject is passed as "target_user_id" in the body (not "user_id"), so
the plugin signs these requests as system calls (user 0): no rate limit, no
enrolment lookup.

Deleting is ordered so that a retry always works: image files first (missing
files are fine), then all database rows in ONE transaction. If a file cannot be
removed the request fails with 500 and the database is left untouched.
"""
import hmac
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DBSession

from db.connection import get_db
from db.models.message import MessageModel
from db.models.message_translation import MessageTranslationModel
from db.models.session import SessionModel
from settings import settings

CHUNK = 500


def require_internal_key(x_internal_api_key: str = Header(default="")) -> None:
    expected = settings.INTERNAL_API_KEY
    if not expected or not hmac.compare_digest(x_internal_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Invalid internal API key")


router = APIRouter(
    prefix="/privacy",
    tags=["privacy"],
    dependencies=[Depends(require_internal_key)],
)


class UserRequest(BaseModel):
    target_user_id: int = Field(ge=1)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _images_root() -> Path:
    if settings.CHAT_IMAGES_DIR:
        return Path(settings.CHAT_IMAGES_DIR)
    return Path(settings.MOODLEDATA_PATH) / "local_ai_system" / "chat_images"


def _chunks(items: list, size: int = CHUNK):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _delete_image_files(relative_paths: list[str]) -> int:
    """Removes the files; a missing file counts as done. Raises 500 if one cannot be removed."""
    root = _images_root().resolve()
    removed = 0
    failed = 0
    folders = set()

    for rel in relative_paths:
        if not rel:
            continue
        target = (root / rel).resolve()
        # Never touch anything outside the images folder, whatever is stored in the database.
        if root != target and root not in target.parents:
            failed += 1
            continue
        try:
            target.unlink()
            removed += 1
        except FileNotFoundError:
            pass
        except OSError:
            failed += 1
        folders.add(target.parent)

    for folder in folders:                      # <root>/<session>/ : drop it when empty
        if folder != root:
            try:
                folder.rmdir()
            except OSError:
                pass

    if failed:
        raise HTTPException(status_code=500, detail=f"{failed} image file(s) could not be deleted")
    return removed


def _delete_sessions(db: DBSession, session_ids: list[str]) -> dict:
    """Deletes sessions with all messages, translations and image files."""
    counts = {"sessions": 0, "messages": 0, "translations": 0, "images": 0}
    if not session_ids:
        return counts

    # 1. files (idempotent)
    for part in _chunks(session_ids):
        rows = db.execute(
            select(MessageModel.image_path).where(
                MessageModel.session_id.in_(part), MessageModel.image_path.isnot(None)
            )
        ).scalars().all()
        counts["images"] += _delete_image_files(list(rows))

    # 2. rows, all or nothing
    try:
        for part in _chunks(session_ids):
            message_ids = select(MessageModel.id).where(MessageModel.session_id.in_(part))
            counts["translations"] += db.execute(
                delete(MessageTranslationModel).where(MessageTranslationModel.message_id.in_(message_ids))
            ).rowcount
            counts["messages"] += db.execute(
                delete(MessageModel).where(MessageModel.session_id.in_(part))
            ).rowcount
            counts["sessions"] += db.execute(
                delete(SessionModel).where(SessionModel.session_id.in_(part))
            ).rowcount
        db.commit()
    except Exception:
        db.rollback()
        raise
    return counts


def _user_session_ids(db: DBSession, user_id: int) -> list[str]:
    return list(db.execute(
        select(SessionModel.session_id).where(SessionModel.user_id == user_id)
    ).scalars().all())


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------
@router.post("/users")
def users_with_data(db: DBSession = Depends(get_db)):
    """Ids of all users who have chat data (Moodle: "which users are in this context")."""
    ids = db.execute(select(SessionModel.user_id).distinct().order_by(SessionModel.user_id)).scalars().all()
    return {"user_ids": [i for i in ids if i > 0]}


@router.post("/user/summary")
def user_summary(body: UserRequest, db: DBSession = Depends(get_db)):
    """Cheap "does this user have data?" check."""
    sessions = db.execute(
        select(func.count()).select_from(SessionModel).where(SessionModel.user_id == body.target_user_id)
    ).scalar_one()
    return {"sessions": sessions}


@router.post("/user/export")
def user_export(body: UserRequest, db: DBSession = Depends(get_db)):
    """Everything stored about one user, as plain JSON."""
    sessions = db.execute(
        select(SessionModel).where(SessionModel.user_id == body.target_user_id).order_by(SessionModel.created_at)
    ).scalars().all()

    result = []
    for s in sessions:
        messages = db.execute(
            select(MessageModel).where(MessageModel.session_id == s.session_id).order_by(MessageModel.id)
        ).scalars().all()
        translations: dict[int, list] = {}
        ids = [m.id for m in messages]
        for part in _chunks(ids):
            for t in db.execute(
                select(MessageTranslationModel).where(MessageTranslationModel.message_id.in_(part))
            ).scalars():
                translations.setdefault(t.message_id, []).append(
                    {"language": t.language, "content": t.content, "created_at": t.created_at}
                )
        result.append({
            "session_id": s.session_id,
            "course_id": s.course_id,
            "title": s.title,
            "language": s.language,
            "archived": not s.is_active,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "is_active_version": bool(m.is_active),
                    "image": m.image_path,
                    "tokens_used": m.tokens_used,
                    "created_at": m.created_at,
                    "translations": translations.get(m.id, []),
                }
                for m in messages
            ],
        })
    return {"sessions": result}


@router.post("/user/delete")
def user_delete(body: UserRequest, db: DBSession = Depends(get_db)):
    """Erases one user's chats completely (rows and image files)."""
    counts = _delete_sessions(db, _user_session_ids(db, body.target_user_id))
    print(f"[privacy] deleted data of user {body.target_user_id}: {counts}", flush=True)
    return {"status": "deleted", **counts}


@router.post("/maintenance")
def maintenance(db: DBSession = Depends(get_db)):
    """
    Retention: deletes every chat whose last activity is older than
    CHAT_RETENTION_DAYS. 0 = retention switched off (nothing is deleted).
    Called daily by the Moodle cron task.
    """
    days = settings.CHAT_RETENTION_DAYS
    if days <= 0:
        return {"status": "retention disabled", "retention_days": 0}

    cutoff = int(time.time()) - days * 86400
    expired = list(db.execute(
        select(SessionModel.session_id).where(SessionModel.updated_at < cutoff)
    ).scalars().all())
    counts = _delete_sessions(db, expired)
    print(f"[privacy] retention {days} days: removed {counts}", flush=True)
    return {"status": "ok", "retention_days": days, **counts}
