import base64
import os
import shutil
import uuid

from settings import settings


_MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class ImageStorage:
    """
    Owns all filesystem access for chat-attached images, under
    <images_root>/<session_id>/<uuid>.<ext>. Deliberately has zero
    dependencies on repositories/DB -- both MessageService and
    SessionService use this, and neither should have to depend on
    the other just to manage image files.
    """

    @staticmethod
    def _chat_images_root() -> str:
        return settings.CHAT_IMAGES_DIR or os.path.join(
            settings.MOODLEDATA_PATH, "local_ai_system", "chat_images"
        )

    def get_abs_path(self, session_id: str, relative_image_path: str) -> str:
        return os.path.join(self._chat_images_root(), relative_image_path)

    def save(self, session_id: str, image_base64: str, image_mime_type: str | None) -> str:
        """
        Decodes and writes the image to disk. Returns a path *relative*
        to the images root (e.g. "7bea81a6.../9f2c1a....jpg") -- never an
        absolute filesystem path, so this keeps working if the storage
        root ever moves (different machine, container, etc).
        """
        ext = _MIME_TO_EXT.get(image_mime_type or "", ".jpg")
        session_dir = os.path.join(self._chat_images_root(), session_id)
        os.makedirs(session_dir, exist_ok=True)

        filename = f"{uuid.uuid4().hex}{ext}"
        abs_path = os.path.join(session_dir, filename)

        with open(abs_path, "wb") as f:
            f.write(base64.b64decode(image_base64))

        return f"{session_id}/{filename}"

    def delete_session_images(self, session_id: str) -> None:
        """
        Removes the entire <images_root>/<session_id>/ directory -- every
        image ever attached to any message (any version/sibling) in this
        session. Safe to call even if the session never had any images.
        """
        session_dir = os.path.join(self._chat_images_root(), session_id)
        if os.path.isdir(session_dir):
            shutil.rmtree(session_dir)
            