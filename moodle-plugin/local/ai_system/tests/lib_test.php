<?php

defined('MOODLE_INTERNAL') || die();

global $CFG;
require_once($CFG->dirroot . '/local/ai_system/lib.php');

/**
 * @covers ::local_ai_system_is_page_allowed_pagetype
 */
class local_ai_system_lib_test extends \advanced_testcase {

    public function test_exact_allowed_pagetypes(): void {
        $this->assertTrue(local_ai_system_is_page_allowed_pagetype('site-index'));
        $this->assertTrue(local_ai_system_is_page_allowed_pagetype('my-index'));
        $this->assertTrue(local_ai_system_is_page_allowed_pagetype('course-index'));
    }

    public function test_substring_match_also_allows(): void {
        // Documents the current (loose) matching behaviour: this passes
        // because "my-index" is a substring, not because it's an exact
        // pagetype Moodle would ever actually produce.
        $this->assertTrue(local_ai_system_is_page_allowed_pagetype('my-index-dashboard'));
    }

    public function test_unrelated_pagetypes_are_denied(): void {
        $this->assertFalse(local_ai_system_is_page_allowed_pagetype('mod-quiz-view'));
        $this->assertFalse(local_ai_system_is_page_allowed_pagetype('admin-setting'));
        $this->assertFalse(local_ai_system_is_page_allowed_pagetype(''));
    }
}