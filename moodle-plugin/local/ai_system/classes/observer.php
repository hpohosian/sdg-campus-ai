<?php
namespace local_ai_system;

defined('MOODLE_INTERNAL') || die();

use local_ai_system\task\reindex_course_task;

class observer {

    /**
     * A general handler for all events indicating that "something in the course has changed."
     * It does not make an HTTP call itself—it merely queues a task in Moodle
     * so as not to block the instructor from saving the page.
     */
    public static function course_changed(\core\event\base $event) {
        $courseid = $event->courseid;

        if (empty($courseid) || $courseid == SITEID) {
            // SITEID — это id=1, главная страница сайта, не настоящий курс.
            return;
        }

        self::queue_reindex($courseid);
    }

    private static function queue_reindex(int $courseid) {
        // Deduplication: if a task for this course is already in the queue —
        // we don't add a second one. This is the "merging" of multiple consecutive edits.
        if (self::has_pending_task($courseid)) {
            return;
        }

        $task = new reindex_course_task();
        $task->set_custom_data(['courseid' => $courseid]);

        \core\task\manager::queue_adhoc_task($task);
    }

    private static function has_pending_task(int $courseid): bool {
        global $DB;

        $records = $DB->get_records('task_adhoc', [
            'classname' => '\\local_ai_system\\task\\reindex_course_task',
        ]);

        foreach ($records as $record) {
            $data = json_decode($record->customdata, true);
            if (!empty($data['courseid']) && (int)$data['courseid'] === $courseid) {
                return true;
            }
        }

        return false;
    }
}