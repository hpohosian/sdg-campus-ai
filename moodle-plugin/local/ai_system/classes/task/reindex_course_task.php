<?php
namespace local_ai_system\task;

defined('MOODLE_INTERNAL') || die();

use local_ai_system\external\api_client;

class reindex_course_task extends \core\task\adhoc_task {

    public function execute() {
        $data = $this->get_custom_data();
        $courseid = $data->courseid ?? null;

        if (empty($courseid)) {
            mtrace("[ai_system] reindex_course_task: no courseid provided, skipping");
            return;
        }

        $client = new api_client();

        try {
            $response = $client->post_internal("/rag/index/{$courseid}", ['reset' => true]);
            mtrace("[ai_system] Course {$courseid} reindex triggered: " . json_encode($response));
        } catch (\moodle_exception $e) {
            mtrace("[ai_system] Course {$courseid} reindex FAILED: " . $e->getMessage());
            throw $e;
        }
    }
}
