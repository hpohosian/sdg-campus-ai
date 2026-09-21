<?php

namespace local_ai_system\chatbot;

defined('MOODLE_INTERNAL') || die();

global $CFG;
require_once($CFG->dirroot . '/local/ai_system/classes/chatbot/service.php');

/**
 * @covers \local_ai_system\chatbot\service
 */
class service_test extends \advanced_testcase {

    public function test_strip_null_image_urls_removes_null_key(): void {
        $messages = [
            ['id' => 1, 'role' => 'user', 'content' => 'hi', 'image_url' => null],
        ];

        $result = service::strip_null_image_urls($messages);

        $this->assertArrayNotHasKey('image_url', $result[0]);
    }

    public function test_strip_null_image_urls_keeps_real_url(): void {
        $messages = [
            ['id' => 2, 'role' => 'assistant', 'content' => 'here', 'image_url' => 'https://example.com/img.png'],
        ];

        $result = service::strip_null_image_urls($messages);

        $this->assertArrayHasKey('image_url', $result[0]);
        $this->assertSame('https://example.com/img.png', $result[0]['image_url']);
    }

    public function test_strip_null_image_urls_leaves_messages_without_the_key_untouched(): void {
        $messages = [
            ['id' => 3, 'role' => 'user', 'content' => 'no image field at all'],
        ];

        $result = service::strip_null_image_urls($messages);

        $this->assertArrayNotHasKey('image_url', $result[0]);
        $this->assertSame($messages, $result);
    }

    public function test_strip_null_image_urls_handles_multiple_messages_independently(): void {
        $messages = [
            ['id' => 1, 'image_url' => null],
            ['id' => 2, 'image_url' => 'https://example.com/a.png'],
            ['id' => 3, 'image_url' => null],
        ];

        $result = service::strip_null_image_urls($messages);

        $this->assertArrayNotHasKey('image_url', $result[0]);
        $this->assertArrayHasKey('image_url', $result[1]);
        $this->assertArrayNotHasKey('image_url', $result[2]);
    }
}