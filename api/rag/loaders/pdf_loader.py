import os
import urllib.parse
import fitz  # pymupdf
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from api.settings import settings
except ModuleNotFoundError:
    from settings import settings

try:
    from api.rag.loaders.pdf_tables import extract_page
except ModuleNotFoundError:
    from rag.loaders.pdf_tables import extract_page


class MoodlePDFLoader:
    """
    Extracts text from PDF files stored in Moodle's file system.
    
    Moodle stores files in moodledata/filedir/ using a content-addressed
    system based on file hash (contenthash).
    """

    def __init__(self, db: Session, moodledata_path: str):
        self.db = db
        self.moodledata_path = moodledata_path

    def load_course_pdfs(self, course_id: int) -> list[dict]:
        """
        Load all PDFs associated with a course.
        Returns list of document dicts with extracted text.
        """
        pdf_files = self._get_course_pdf_files(course_id)
        documents = []

        for pdf in pdf_files:
            page_texts, tables = self._extract_pdf(pdf["contenthash"])
            text_content = "\n\n".join(page_texts).strip()
            table_chars = sum(len(t["text"]) for t in tables)
            if len(text_content) + table_chars > 100:
                documents.append({
                    "text": text_content,
                    # Per-page texts: ingestion uses them to store the page
                    # number of every chunk ("page"), so citations can link
                    # to the exact page (file.pdf#page=N).
                    "page_texts": page_texts,
                    # Tables, each stored as its own chunk (not cut apart
                    # by the chunker): see pdf_tables.py.
                    "tables": tables,
                    "metadata": {
                        "course_id": course_id,
                        "source_type": "pdf",
                        "source_name": pdf["filename"],
                        "source": pdf["filename"],
                        "file_url": pdf["file_url"],
                        "section": "",
                    }
                })
                print(f"[pdf_loader] Loaded: {pdf['filename']} ({len(text_content)} chars"
                      f"{f', {len(tables)} table chunks' if tables else ''})")
            else:
                print(f"[pdf_loader] Skipped (no text): {pdf['filename']}")

        print(f"[pdf_loader] Course {course_id}: {len(documents)} PDFs loaded")
        return documents

    def _get_course_pdf_files(self, course_id: int) -> list[dict]:
        """Get all PDF file records for a course from Moodle DB."""
        rows = self.db.execute(text("""
            SELECT DISTINCT f.filename, f.contenthash, f.filesize,
                            f.contextid, f.component, f.filearea, f.itemid
            FROM mdl_files f
            JOIN mdl_context ctx ON ctx.id = f.contextid
            WHERE f.mimetype = 'application/pdf'
            AND f.filename != '.'
            AND f.filesize > 0
            AND (
                (ctx.contextlevel = 70 AND ctx.instanceid IN (
                    SELECT id FROM mdl_course_modules WHERE course = :course_id
                ))
                OR
                (ctx.contextlevel = 50 AND ctx.instanceid = :course_id)
            )
            ORDER BY f.filename
        """), {"course_id": course_id}).fetchall()

        return [
            {
                "filename": row.filename,
                "contenthash": row.contenthash,
                "file_url": self._build_file_url(
                    contextid=row.contextid,
                    component=row.component,
                    filearea=row.filearea,
                    itemid=row.itemid,
                    filename=row.filename,
                ),
            }
            for row in rows
        ]

    def _build_file_url(self, contextid: int, component: str, filearea: str, itemid: int, filename: str) -> str:
        """
        Builds a direct Moodle pluginfile.php URL for a stored file, e.g.:
            http://127.0.0.1/pluginfile.php/45/mod_resource/content/1/Butin2010.pdf

        This is the standard way Moodle serves files that live in mdl_files
        — clicking it downloads/opens the file directly, same as clicking
        it from within the course page.
        """
        encoded_filename = urllib.parse.quote(filename)
        return (
            f"{settings.MOODLE_BASE_URL}/pluginfile.php/"
            f"{contextid}/{component}/{filearea}/{itemid}/{encoded_filename}"
        )

    def _get_file_path(self, contenthash: str) -> str:
        """
        Moodle stores files at: moodledata/filedir/XX/YY/contenthash
        where XX = first 2 chars, YY = next 2 chars of hash.
        """
        return os.path.join(
            self.moodledata_path,
            "filedir",
            contenthash[:2],
            contenthash[2:4],
            contenthash,
        )

    def _extract_pdf(self, contenthash: str) -> tuple[list[str], list[dict]]:
        """
        Text of every page (index 0 = page 1) WITHOUT tables, and the
        tables as separate chunks: [{"page": n, "text": markdown,
        "embed_text": short description for the search}].
        """
        file_path = self._get_file_path(contenthash)

        if not os.path.exists(file_path):
            return [], []

        try:
            doc = fitz.open(file_path)
            pages_text, tables = [], []
            for number, page in enumerate(doc, start=1):
                text, page_tables = extract_page(page, number)
                pages_text.append(text)
                tables += [{"page": number, **t} for t in page_tables]
            doc.close()
            return pages_text, tables
        except Exception as e:
            print(f"[pdf_loader] Error reading {contenthash}: {e}")
            return [], []

    def _extract_pdf_pages(self, contenthash: str) -> list[str]:
        """Text of every page (index 0 = page 1), tables not included."""
        return self._extract_pdf(contenthash)[0]

    def _extract_pdf_text(self, contenthash: str) -> str:
        """Extract the whole text of a PDF (pages joined)."""
        return "\n\n".join(self._extract_pdf_pages(contenthash)).strip()
        