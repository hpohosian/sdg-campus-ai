import re
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from api.settings import settings
except ModuleNotFoundError:
    from settings import settings


def _moodle_url(path: str) -> str:
    """Absolute Moodle URL. Stored as "source_url" so citations of pages,
    books and sections become links (and source cards), like PDFs."""
    return f"{settings.MOODLE_BASE_URL.rstrip('/')}{path}"


def clean_html(html: str) -> str:
    """Remove HTML tags and clean up whitespace."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class MoodleDBLoader:
    """
    Loads course content directly from Moodle database.
    
    Extracts text from:
    - course_sections (section summaries)
    - mdl_page (text pages)
    - mdl_book_chapters (book chapters)
    - mdl_label (text labels)
    """

    def __init__(self, db: Session):
        self.db = db

    def load_course(self, course_id: int) -> list[dict]:
        """
        Load all text content for a course.
        
        Returns list of dicts:
        {
            "text": str,
            "metadata": {
                "course_id": int,
                "source_type": str,
                "source_name": str,
                "section": str,
            }
        }
        """
        documents = []

        documents.extend(self._load_sections(course_id))
        documents.extend(self._load_pages(course_id))
        documents.extend(self._load_book_chapters(course_id))
        documents.extend(self._load_labels(course_id))

        # Filter out empty documents
        documents = [d for d in documents if len(d["text"]) > 50]

        print(f"[moodle_loader] Course {course_id}: {len(documents)} documents loaded")
        return documents

    def _load_sections(self, course_id: int) -> list[dict]:
        """Load course section summaries."""
        rows = self.db.execute(text("""
            SELECT id, name, summary, section
            FROM mdl_course_sections
            WHERE course = :course_id
            AND (summary IS NOT NULL AND summary != '')
            ORDER BY section
        """), {"course_id": course_id}).fetchall()

        docs = []
        for row in rows:
            text_content = clean_html(row.summary)
            if text_content:
                docs.append({
                    "text": text_content,
                    "metadata": {
                        "course_id": course_id,
                        "source_type": "section",
                        "source_name": row.name or f"Section {row.id}",
                        "source": row.name or f"Section {row.section}",
                        "section": row.name or "",
                        "source_url": _moodle_url(f"/course/view.php?id={course_id}#section-{row.section}"),
                    }
                })
        return docs

    def _load_pages(self, course_id: int) -> list[dict]:
        """Load mdl_page text content."""
        rows = self.db.execute(text("""
            SELECT p.id, p.name, p.content, cs.name as section_name, cm.id as cmid
            FROM mdl_page p
            LEFT JOIN mdl_course_modules cm ON cm.instance = p.id
                AND cm.module = (SELECT id FROM mdl_modules WHERE name = 'page')
                AND cm.course = p.course
            LEFT JOIN mdl_course_sections cs ON cs.id = cm.section
            WHERE p.course = :course_id
        """), {"course_id": course_id}).fetchall()

        docs = []
        for row in rows:
            text_content = clean_html(row.content)
            if text_content:
                docs.append({
                    "text": f"{row.name}\n\n{text_content}",
                    "metadata": {
                        "course_id": course_id,
                        "source_type": "page",
                        "source_name": row.name,
                        "source": row.name,
                        "section": row.section_name or "",
                        "source_url": _moodle_url(
                            f"/mod/page/view.php?id={row.cmid}" if row.cmid
                            else f"/course/view.php?id={course_id}"
                        ),
                    }
                })
        return docs

    def _load_book_chapters(self, course_id: int) -> list[dict]:
        """Load book chapters."""
        rows = self.db.execute(text("""
            SELECT b.name as book_name, bc.id as chapter_id, bc.title, bc.content, bc.pagenum,
                   cm.id as cmid
            FROM mdl_book b
            JOIN mdl_book_chapters bc ON bc.bookid = b.id
            LEFT JOIN mdl_course_modules cm ON cm.instance = b.id
                AND cm.module = (SELECT id FROM mdl_modules WHERE name = 'book')
                AND cm.course = b.course
            WHERE b.course = :course_id
            ORDER BY b.id, bc.pagenum
        """), {"course_id": course_id}).fetchall()

        docs = []
        for row in rows:
            text_content = clean_html(row.content)
            if text_content:
                docs.append({
                    "text": f"{row.book_name} — {row.title}\n\n{text_content}",
                    "metadata": {
                        "course_id": course_id,
                        "source_type": "book_chapter",
                        "source_name": f"{row.book_name} — {row.title}",
                        "source": f"{row.book_name} — {row.title}",
                        "section": row.book_name,
                        "source_url": _moodle_url(
                            f"/mod/book/view.php?id={row.cmid}&chapterid={row.chapter_id}" if row.cmid
                            else f"/course/view.php?id={course_id}"
                        ),
                    }
                })
        return docs

    def _load_labels(self, course_id: int) -> list[dict]:
        """Load label text blocks."""
        rows = self.db.execute(text("""
            SELECT l.id, l.name, l.intro
            FROM mdl_label l
            WHERE l.course = :course_id
            AND l.intro IS NOT NULL
            AND l.intro != ''
        """), {"course_id": course_id}).fetchall()

        docs = []
        for row in rows:
            text_content = clean_html(row.intro)
            if text_content:
                docs.append({
                    "text": text_content,
                    "metadata": {
                        "course_id": course_id,
                        "source_type": "label",
                        "source_name": row.name or f"Label {row.id}",
                        "source": row.name or f"Label {row.id}",
                        "section": "",
                        # Labels have no page of their own: link to the course. The
                        # #label-… anchor marks it as a SOURCE link for the UI
                        # (a bare course link is the "from <course>" part).
                        "source_url": _moodle_url(f"/course/view.php?id={course_id}#label-{row.id}"),
                    }
                })
        return docs
    