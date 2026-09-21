<?php

namespace local_ai_system\privacy;

defined('MOODLE_INTERNAL') || die();

global $CFG;
require_once($CFG->dirroot . '/local/ai_system/classes/privacy/provider.php');

use core_privacy\local\metadata\collection;

/**
 * @covers \local_ai_system\privacy\provider
 */
class provider_test extends \advanced_testcase {

    public function test_get_metadata_declares_expected_tables(): void {
        $collection = new collection('local_ai_system');
        $result = provider::get_metadata($collection);

        $tablenames = [];
        foreach ($result->get_collection() as $item) {
            if (method_exists($item, 'get_name')) {
                $tablenames[] = $item->get_name();
            }
        }

        $this->assertContains('local_ai_system_sessions', $tablenames);
        $this->assertContains('local_ai_system_messages', $tablenames);
        $this->assertContains('local_ai_system_message_translations', $tablenames);
    }
}