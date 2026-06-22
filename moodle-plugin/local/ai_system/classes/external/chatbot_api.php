<?php

namespace local_ai_system\external;

use core_external\external_api;
use core_external\external_function_parameters;
use core_external\external_value;
use core_external\external_single_structure;
use core_external\external_multiple_structure;

defined('MOODLE_INTERNAL') || die();

class chatbot_api extends external_api {

    // =========================
    // SEND MESSAGE
    // =========================
    public static function send_message_parameters() {
        return new external_function_parameters([
            'session_id' => new external_value(PARAM_TEXT, 'Session ID'),
            'message' => new external_value(PARAM_TEXT, 'User message'),
            'course_id' => new external_value(PARAM_INT, 'Course ID', VALUE_OPTIONAL)
        ]);
    }

    public static function send_message($session_id, $message, $course_id = null) {

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
            $params['session_id'],
            $params['message']
        );

        return [
            'message'    => $result['message'] ?? 'No response',
            'session_id' => $result['session_id'] ?? $params['session_id']
        ];
    }

    public static function send_message_returns() {
        return new external_single_structure([
            'message'    => new external_value(PARAM_RAW, 'Bot response text'),
            'session_id' => new external_value(PARAM_TEXT, 'Session ID')
        ]);
    }


    // =========================
    // CREATE SESSION
    // =========================
    public static function create_session_parameters() {
        return new external_function_parameters([
            'title' => new external_value(PARAM_TEXT, 'Session title', VALUE_DEFAULT, 'New Chat'),
            'course_id' => new external_value(PARAM_INT, 'Course ID', VALUE_DEFAULT, 0)
        ]);
    }

    public static function create_session($title = 'New Chat', $course_id = 0) {
        global $USER;

        $params = self::validate_parameters(
            self::create_session_parameters(),
            ['title' => $title, 'course_id' => $course_id]
        );

        self::validate_context(\context_system::instance());
        require_capability('local_ai_system:use_chatbot', \context_system::instance());

        $service = new \local_ai_system\chatbot\service();

        return $service->create_session($USER->id, $params['title'], $params['course_id']);
    }

    public static function create_session_returns() {
        return new external_single_structure([
            'session_id' => new external_value(PARAM_TEXT),
            'title' => new external_value(PARAM_TEXT)
        ]);
    }


    // =========================
    // GET SESSIONS
    // =========================
    public static function get_sessions_parameters() {
        return new external_function_parameters([]);
    }

    public static function get_sessions() {

        $context = \context_system::instance();

        self::validate_context($context);

        require_capability(
            'local_ai_system:use_chatbot',
            $context
        );

        global $USER;

        $service = new \local_ai_system\chatbot\service();

        return $service->get_sessions($USER->id);
    }

    public static function get_sessions_returns() {

        return new external_multiple_structure(
            new external_single_structure([
                'session_id' => new external_value(
                    PARAM_TEXT
                ),

                'title' => new external_value(
                    PARAM_TEXT
                ),

                'created_at' => new external_value(
                    PARAM_INT,
                    'Created timestamp',
                    VALUE_OPTIONAL
                ),

                'updated_at' => new external_value(
                    PARAM_INT,
                    'Updated timestamp',
                    VALUE_OPTIONAL
                ),

                'is_active'  => new external_value(
                    PARAM_INT,
                    'Active state',
                    VALUE_OPTIONAL
                ),
            ])
        );
    }


    // =========================
    // UPDATE SESSION
    // =========================

    public static function update_session_parameters() {

        return new external_function_parameters([
            'session_id' => new external_value(
                PARAM_TEXT,
                'Session ID'
            ),

            'title' => new external_value(
                PARAM_TEXT,
                'New title'
            )
        ]);
    }

    public static function update_session($session_id, $title) {

        $params = self::validate_parameters(
            self::update_session_parameters(),
            [
                'session_id' => $session_id,
                'title' => $title
            ]
        );

        $context = \context_system::instance();
        self::validate_context($context);
        require_capability('local_ai_system:use_chatbot', $context);

        global $USER;

        $service = new \local_ai_system\chatbot\service();

        $service->update_session(
            $params['session_id'],
            ['title' => $params['title']],
            $USER->id
        );

        return ['success' => true];
    }


    public static function update_session_returns() {

        return new external_single_structure([
            'success' => new external_value(
                PARAM_BOOL
            )
        ]);
    }


    // =========================
    // DELETE SESSION
    // =========================

    public static function delete_session_parameters() {

        return new external_function_parameters([
            'session_id' => new external_value(
                PARAM_TEXT
            )
        ]);
    }

    public static function delete_session(
        $session_id
    ) {

        $params = self::validate_parameters(
            self::delete_session_parameters(),
            [
                'session_id' => $session_id
            ]
        );

        $context = \context_system::instance();

        self::validate_context($context);

        require_capability(
            'local_ai_system:use_chatbot',
            $context
        );

        global $USER;

        $service = new \local_ai_system\chatbot\service();

        $service->delete_session(
            $params['session_id'],
            $USER->id
        );

        return ['success' => true];
    }

    public static function delete_session_returns() {

        return new external_single_structure([
            'success' => new external_value(
                PARAM_BOOL
            )
        ]);
    }


    // =========================
    // ARCHIVE SESSION
    // =========================

    public static function archive_session_parameters() {

        return new external_function_parameters([
            'session_id' => new external_value(
                PARAM_TEXT
            )
        ]);
    }

    public static function archive_session(
        $session_id
    ) {

        $params = self::validate_parameters(
            self::archive_session_parameters(),
            [
                'session_id' => $session_id
            ]
        );

        $context = \context_system::instance();

        self::validate_context($context);

        require_capability(
            'local_ai_system:use_chatbot',
            $context
        );

        global $USER;

        $service = new \local_ai_system\chatbot\service();

        $service->archive_session(
            $params['session_id'],
            $USER->id
        );

        return ['success' => true];
    }

    public static function archive_session_returns() {

        return new external_single_structure([
            'success' => new external_value(
                PARAM_BOOL
            )
        ]);
    }


    // =========================
    // DEARCHIVE SESSION
    // =========================

    public static function dearchive_session_parameters() {

        return new external_function_parameters([
            'session_id' => new external_value(
                PARAM_TEXT
            )
        ]);
    }

    public static function dearchive_session(
        $session_id
    ) {

        $params = self::validate_parameters(
            self::dearchive_session_parameters(),
            [
                'session_id' => $session_id
            ]
        );

        $context = \context_system::instance();

        self::validate_context($context);

        require_capability(
            'local_ai_system:use_chatbot',
            $context
        );

        global $USER;

        $service = new \local_ai_system\chatbot\service();

        $service->dearchive_session(
            $params['session_id'],
            $USER->id
        );

        return ['success' => true];
    }

    public static function dearchive_session_returns() {

        return new external_single_structure([
            'success' => new external_value(
                PARAM_BOOL
            )
        ]);
    }


    // =========================
    // GET MESSAGES - PARAMETERS
    // =========================
    public static function get_messages_parameters() {

        return new external_function_parameters([
            'session_id' => new external_value(
                PARAM_TEXT,
                'Session ID'
            )
        ]);
    }

    // =========================
    // GET MESSAGES - MAIN LOGIC
    // =========================
    public static function get_messages(
        $session_id
    ) {

        $params = self::validate_parameters(
            self::get_messages_parameters(),
            [
                'session_id' => $session_id
            ]
        );

        $context = \context_system::instance();

        self::validate_context($context);

        require_capability(
            'local_ai_system:use_chatbot',
            $context
        );

        $service = new \local_ai_system\chatbot\service();

        global $USER;

        return $service->get_messages(
            $params['session_id'],
            $USER->id
        );
    }

    // =========================
    // GET MESSAGES - RETURNS
    // =========================
    public static function get_messages_returns() {

        return new external_multiple_structure(
            new external_single_structure([

                'id' => new external_value(
                    PARAM_INT,
                    'Message ID',
                    VALUE_OPTIONAL
                ),

                'role' => new external_value(
                    PARAM_TEXT
                ),

                'content' => new external_value(
                    PARAM_RAW
                ),

                'created_at' => new external_value(
                    PARAM_TEXT,
                    'Timestamp',
                    VALUE_OPTIONAL
                )
            ])
        );
    }


    // =========================
    // STREAM MESSAGE
    // =========================

    public static function stream_message_parameters() {

        return new external_function_parameters([
            'session_id' => new external_value(
                PARAM_TEXT,
                'Session ID'
            ),

            'message' => new external_value(
                PARAM_RAW,
                'User message'
            )
        ]);
    }

    public static function stream_message(
        $session_id,
        $message
    ) {

        $params = self::validate_parameters(
            self::stream_message_parameters(),
            [
                'session_id' => $session_id,
                'message' => $message
            ]
        );

        $context = \context_system::instance();

        self::validate_context($context);

        require_capability(
            'local/ai_system:use_chatbot',
            $context
        );

        $service = new \local_ai_system\chatbot\service();

        return $service->stream_message(
            $params['session_id'],
            $params['message']
        );
    }

    public static function stream_message_returns() {

        return new external_value(
            PARAM_RAW,
            'Streaming response'
        );
    }

}
