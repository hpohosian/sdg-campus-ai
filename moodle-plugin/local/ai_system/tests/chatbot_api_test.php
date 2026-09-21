<?php

namespace local_ai_system\external;

defined('MOODLE_INTERNAL') || die();

global $CFG;
require_once($CFG->dirroot . '/local/ai_system/classes/external/chatbot_api.php');

/**
 * @covers \local_ai_system\external\chatbot_api
 */
class chatbot_api_test extends \advanced_testcase {

    /**
     * A logged-in user with the default capability set (i.e. the plugin's
     * intended, "everything just works out of the box") must be allowed
     * to create a session.
     */
    public function test_create_session_allowed_for_default_user(): void {
        $this->resetAfterTest(true);

        $user = $this->getDataGenerator()->create_user();
        $this->setUser($user);

        $result = chatbot_api::create_session('Test chat');

        $this->assertArrayHasKey('session_id', $result);
        $this->assertNotEmpty($result['session_id']);
    }

    /**
     * A user whose capability has been explicitly prohibited must be
     * rejected -- this is what actually verifies the capability check
     * exists and points at the right name (local/ai_system:use_chatbot).
     */
    public function test_create_session_denied_without_capability(): void {
        $this->resetAfterTest(true);

        $user = $this->getDataGenerator()->create_user();
        $this->setUser($user);

        $roleid = $this->getDataGenerator()->create_role();
        assign_capability(
            'local/ai_system:use_chatbot',
            CAP_PROHIBIT,
            $roleid,
            \context_system::instance()
        );
        role_assign($roleid, $user->id, \context_system::instance());
        accesslib_clear_all_caches_for_unit_testing();

        $this->expectException(\required_capability_exception::class);

        chatbot_api::create_session('Test chat');
    }

    /**
     * A logged-out user must never reach the capability check at all --
     * should fail earlier, on validate_context()/require_login().
     */
    public function test_create_session_denied_when_not_logged_in(): void {
        $this->resetAfterTest(true);

        $this->setUser(0); // Not logged in.

        $this->expectException(\require_login_exception::class);

        chatbot_api::create_session('Test chat');
    }
}
