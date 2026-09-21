<?php

namespace local_ai_system\external;

defined('MOODLE_INTERNAL') || die();

global $CFG;
require_once($CFG->dirroot . '/local/ai_system/classes/external/chatbot_api.php');

/**
 * @covers \local_ai_system\external\chatbot_api
 */
class capabilities_test extends \advanced_testcase {

    private function prohibit_capability_for_current_user(): void {
        global $USER;

        $roleid = $this->getDataGenerator()->create_role();
        assign_capability('local/ai_system:use_chatbot', CAP_PROHIBIT, $roleid, \context_system::instance());
        role_assign($roleid, $USER->id, \context_system::instance());
        accesslib_clear_all_caches_for_unit_testing();
    }

    public function test_get_sessions_denied_without_capability(): void {
        $this->resetAfterTest(true);
        $this->setUser($this->getDataGenerator()->create_user());
        $this->prohibit_capability_for_current_user();

        $this->expectException(\required_capability_exception::class);
        chatbot_api::get_sessions();
    }

    public function test_update_session_denied_without_capability(): void {
        $this->resetAfterTest(true);
        $this->setUser($this->getDataGenerator()->create_user());
        $this->prohibit_capability_for_current_user();

        $this->expectException(\required_capability_exception::class);
        chatbot_api::update_session('some-id', 'New title');
    }

    public function test_archive_session_denied_without_capability(): void {
        $this->resetAfterTest(true);
        $this->setUser($this->getDataGenerator()->create_user());
        $this->prohibit_capability_for_current_user();

        $this->expectException(\required_capability_exception::class);
        chatbot_api::archive_session('some-id');
    }

    public function test_dearchive_session_denied_without_capability(): void {
        $this->resetAfterTest(true);
        $this->setUser($this->getDataGenerator()->create_user());
        $this->prohibit_capability_for_current_user();

        $this->expectException(\required_capability_exception::class);
        chatbot_api::dearchive_session('some-id');
    }

    public function test_save_partial_message_denied_without_capability(): void {
        $this->resetAfterTest(true);
        $this->setUser($this->getDataGenerator()->create_user());
        $this->prohibit_capability_for_current_user();

        $this->expectException(\required_capability_exception::class);
        chatbot_api::save_partial_message('some-id', 'partial text');
    }

    public function test_send_message_denied_without_capability(): void {
        $this->resetAfterTest(true);
        $this->setUser($this->getDataGenerator()->create_user());
        $this->prohibit_capability_for_current_user();

        $this->expectException(\required_capability_exception::class);
        chatbot_api::send_message('some-id', 'hello');
    }
}