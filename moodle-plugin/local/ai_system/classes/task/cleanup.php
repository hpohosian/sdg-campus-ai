<?php

namespace local_ai_system\task;

use local_ai_system\external\api_client;

defined('MOODLE_INTERNAL') || die();

/**
 * Daily retention cleanup. The chats live in the backend's own database, so
 * Moodle only has to ask the backend to delete everything older than its
 * CHAT_RETENTION_DAYS setting (0 = retention off, nothing is deleted).
 */
class cleanup extends \core\task\scheduled_task {

    public function get_name() {
        return get_string('cleanup_task', 'local_ai_system');
    }

    public function execute() {
        // Throws if the backend is unreachable or refuses, so the failure shows up in the task log.
        $result = (new api_client())->post_internal_strict('/privacy/maintenance');
        mtrace('local_ai_system cleanup: ' . json_encode($result));
    }
}
