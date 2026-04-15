<?php

namespace local_ai_system\external;

use core_external\external_api;
use core_external\external_function_parameters;
use core_external\external_value;
use core_external\external_single_structure;

defined('MOODLE_INTERNAL') || die();

class chatbot_api extends external_api {

    // =========================
    // SEND MESSAGE - PARAMETERS
    // =========================
    public static function send_message_parameters() {
        return new external_function_parameters([
            'session_id' => new external_value(PARAM_TEXT, 'Session ID'),
            'message' => new external_value(PARAM_TEXT, 'User message'),
            'course_id' => new external_value(PARAM_INT, 'Course ID', VALUE_OPTIONAL)
        ]);
    }

    // =========================
    // SEND MESSAGE - MAIN LOGIC
    // =========================
    public static function send_message($session_id, $message, $course_id = null) {

        global $USER;

        // Input Validation
        $params = self::validate_parameters(
            self::send_message_parameters(),
            [
                'session_id' => $session_id,
                'message' => $message,
                'course_id' => $course_id
            ]
        );

        // Context checking
        $context = \context_system::instance();
        self::validate_context($context);

        // Permissions check
        require_capability('local/ai_system:use_chatbot', $context);

        // Calling your service
        $service = new \local_ai_system\chatbot\service();

        $result = $service->send_message(
            $USER->id,
            $params['session_id'],
            $params['message']
        );

        return [
            'message'    => $result['message'] ?? 'No response',
            'session_id' => $result['session_id'] ?? $params['session_id']
        ];
    }

    // =========================
    // SEND MESSAGE - RETURNS
    // =========================
    public static function send_message_returns() {
        return new external_single_structure([
            'message'    => new external_value(PARAM_RAW, 'Bot response text'),
            'session_id' => new external_value(PARAM_TEXT, 'Session ID')
        ]);
    }

    // =========================
    // GET HISTORY - PARAMETERS
    // =========================
    public static function get_history_parameters() {
        return new external_function_parameters([
            'session_id' => new external_value(PARAM_TEXT, 'Session ID')
        ]);
    }

    // =========================
    // GET HISTORY - MAIN LOGIC
    // =========================
    public static function get_history($session_id) {

        global $USER;

        $params = self::validate_parameters(
            self::get_history_parameters(),
            [
                'session_id' => $session_id
            ]
        );

        $context = \context_system::instance();
        self::validate_context($context);

        require_capability('local/ai_system:use_chatbot', $context);

        $service = new \local_ai_system\chatbot\service();

        $history = $service->get_history(
            $USER->id,
            $params['session_id']
        );

        return [
            'messages' => json_encode($history)
        ];
    }

    // =========================
    // GET HISTORY - RETURNS
    // =========================
    public static function get_history_returns() {
        return new external_single_structure([
            'messages' => new external_value(PARAM_RAW, 'Chat history JSON')
        ]);
    }
}
