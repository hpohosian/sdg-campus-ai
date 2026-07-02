import os
import fitz  # pymupdf
from sqlalchemy import text
from sqlalchemy.orm import Session


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
            text_content = self._extract_pdf_text(pdf["contenthash"])
            if text_content and len(text_content) > 100:
                documents.append({
                    "text": text_content,
                    "metadata": {
                        "course_id": course_id,
                        "source_type": "pdf",
                        "source_name": pdf["filename"],
                        "source": pdf["filename"],
                        "section": "",
                    }
                })
                print(f"[pdf_loader] Loaded: {pdf['filename']} ({len(text_content)} chars)")
            else:
                print(f"[pdf_loader] Skipped (no text): {pdf['filename']}")

        print(f"[pdf_loader] Course {course_id}: {len(documents)} PDFs loaded")
        return documents

    def _get_course_pdf_files(self, course_id: int) -> list[dict]:
        """Get all PDF file records for a course from Moodle DB."""
        rows = self.db.execute(text("""
            SELECT DISTINCT f.filename, f.contenthash, f.filesize
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
            {"filename": row.filename, "contenthash": row.contenthash}
            for row in rows
        ]

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

    def _extract_pdf_text(self, contenthash: str) -> str:
        """Extract text from PDF using PyMuPDF."""
        file_path = self._get_file_path(contenthash)

        if not os.path.exists(file_path):
            return ""

        try:
            doc = fitz.open(file_path)
            pages_text = []
            for page in doc:
                pages_text.append(page.get_text())
            doc.close()
            return "\n\n".join(pages_text).strip()
        except Exception as e:
            print(f"[pdf_loader] Error reading {contenthash}: {e}")
            return ""