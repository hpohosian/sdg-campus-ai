try:
    from api.settings import settings
except ModuleNotFoundError:
    from settings import settings


def format_course_link(course_id: int, course_name: str | None) -> str:
    """
    Builds a ready-to-use markdown link for a course, e.g.:
        "[PtX-Lab-Challenge](http://127.0.0.1/course/view.php?id=12)"

    This is built here, in trusted code, rather than left for the LLM to
    construct — the LLM only ever copies this string as-is into its
    answer, it never has to (or is allowed to) invent the URL itself.

    course_name: pass None if the course lookup failed (deleted course,
    stale id, etc.) — falls back to "Course {id}" so citations still
    make sense even without a friendly name.
    """
    name = course_name or f"Course {course_id}"
    url = f"{settings.MOODLE_BASE_URL}/course/view.php?id={course_id}"
    return f"[{name}]({url})"


def build_course_links(course_names: dict[int, str]) -> dict[int, str]:
    """Bulk version: {course_id: fullname} -> {course_id: markdown_link}."""
    return {
        course_id: format_course_link(course_id, name)
        for course_id, name in course_names.items()
    }
    