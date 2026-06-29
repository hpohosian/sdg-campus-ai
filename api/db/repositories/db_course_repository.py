from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text


class CourseRepository:
    """
    A repository for reading course data directly from native Moodle tables.
    Read-only—we never write to Moodle tables (mdl_*) from the Python service;
    that is exclusively the responsibility of Moodle itself or the PHP plugin.
    """

    def __init__(self, db: DBSession):
        self.db = db

    def get_all_course_ids(self) -> list[int]:
        """Returns the IDs of all actual Moodle courses (excluding the placeholder site with ID 1)."""
        rows = self.db.execute(
            text("SELECT id FROM mdl_course WHERE id != 1 ORDER BY id")
        ).fetchall()
        return [row.id for row in rows]

    def course_exists(self, course_id: int) -> bool:
        """Pre-indexing check — to avoid indexing a non-existent exchange rate."""
        row = self.db.execute(
            text("SELECT id FROM mdl_course WHERE id = :course_id"),
            {"course_id": course_id},
        ).fetchone()
        return row is not None

    def get_course_name(self, course_id: int) -> str | None:
        """Useful for logs/API responses—so you can see not just the ID, but also the course name."""
        row = self.db.execute(
            text("SELECT fullname FROM mdl_course WHERE id = :course_id"),
            {"course_id": course_id},
        ).fetchone()
        return row.fullname if row else None
    
    def get_enrolled_course_ids(self, user_id: int) -> list[int]:
        """
        Returns course IDs the user is actively enrolled in.
        Used as the safety boundary for global (cross-course) search —
        a user must never receive context from a course they're not enrolled in.
        """
        rows = self.db.execute(
            text("""
                SELECT DISTINCT e.courseid
                FROM mdl_user_enrolments ue
                JOIN mdl_enrol e ON e.id = ue.enrolid
                WHERE ue.userid = :user_id
                AND ue.status = 0
                AND e.status = 0
                AND e.courseid != 1
            """),
            {"user_id": user_id},
        ).fetchall()
        return [row.courseid for row in rows]