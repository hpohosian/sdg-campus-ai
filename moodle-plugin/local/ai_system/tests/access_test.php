<?php

defined('MOODLE_INTERNAL') || die();

class local_ai_system_access_test extends \advanced_testcase {

    public function test_capabilities_have_expected_shape(): void {
        global $CFG;
        $capabilities = [];
        require($CFG->dirroot . '/local/ai_system/db/access.php');

        $this->assertArrayHasKey('local/ai_system:use_chatbot', $capabilities);
        $this->assertSame(CONTEXT_SYSTEM, $capabilities['local/ai_system:use_chatbot']['contextlevel']);
        $this->assertSame(CAP_ALLOW, $capabilities['local/ai_system:use_chatbot']['archetypes']['user']);

        $this->assertArrayHasKey('local/ai_system:view_history', $capabilities);
    }

    /**
     * This is the test that would have caught the original
     * "local_ai_system:" vs "local/ai_system:" naming bug immediately,
     * at install time, instead of us discovering it live via a
     * "nopermissions" error in the browser.
     */
    public function test_capability_is_recognised_by_moodle_after_install(): void {
        $this->assertNotFalse(get_capability_info('local/ai_system:use_chatbot'));
    }
}