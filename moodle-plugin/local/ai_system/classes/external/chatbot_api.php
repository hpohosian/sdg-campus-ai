<?php

namespace local_ai_system\external;

use core_external\external_api;
use core_external\external_function_parameters;
use core_external\external_value;
use core_external\external_single_structure;
use core_external\external_multiple_structure;

defined('MOODLE_INTERNAL') || die();

class chatbot_api extends external_api {


    private const UNSET = '__unset__';


    private const UNSET_COURSE_ID = -1; // real Moodle course ids are always >= 1


    // =========================
    // SEND MESSAGE
    // =========================
    public static function send_message_parameters() {
        return new external_function_parameters([
            'session_id' => new external_value(PARAM_TEXT, 'Session ID'),
            'message' => new external_value(PARAM_TEXT, 'User message'),
            'course_id' => new external_value(PARAM_INT, 'Course ID', VALUE_DEFAULT, 0)
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
        require_capability('local/ai_system:use_chatbot', \context_system::instance());

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
            'local/ai_system:use_chatbot',
            $context
        );

        global $USER;

        $service = new \local_ai_system\chatbot\service();

        return $service->get_sessions($USER->id);
    }

    public static function get_sessions_returns() {
        return new external_multiple_structure(
            new external_single_structure([
                'session_id' => new external_value(PARAM_TEXT),
                'title'      => new external_value(PARAM_TEXT),
                'course_id'  => new external_value(PARAM_INT, 'Course ID', VALUE_OPTIONAL),
                'language'   => new external_value(PARAM_TEXT, 'Display language', VALUE_OPTIONAL),
                'created_at' => new external_value(PARAM_INT, 'Created timestamp', VALUE_OPTIONAL),
                'updated_at' => new external_value(PARAM_INT, 'Updated timestamp', VALUE_OPTIONAL),
                'is_active'  => new external_value(PARAM_INT, 'Active state', VALUE_OPTIONAL),
            ])
        );
    }


    // =========================
    // UPDATE SESSION
    // =========================
    public static function update_session_parameters() {
        return new external_function_parameters([
            'session_id' => new external_value(PARAM_TEXT, 'Session ID'),
            'title'      => new external_value(PARAM_TEXT, 'New title', VALUE_DEFAULT, self::UNSET),
            'language'   => new external_value(PARAM_TEXT, 'Display language ("" resets to original)', VALUE_DEFAULT, self::UNSET),
            'course_id'  => new external_value(PARAM_INT, 'Course ID (0 = global/all courses)', VALUE_DEFAULT, self::UNSET_COURSE_ID), // NEW
        ]);
    }

    public static function update_session($session_id, $title = self::UNSET, $language = self::UNSET, $course_id = self::UNSET_COURSE_ID) {  // CHANGED

        $params = self::validate_parameters(
            self::update_session_parameters(),
            [
                'session_id' => $session_id,
                'title'      => $title,
                'language'   => $language,
                'course_id'  => $course_id,
            ]
        );

        $context = \context_system::instance();
        self::validate_context($context);
        require_capability('local/ai_system:use_chatbot', $context);

        global $USER;

        // Собираем тело запроса только из полей, которые реально пришли с фронта
        $data = [];

        if ($params['title'] !== self::UNSET) {
            $data['title'] = $params['title'];
        }

        if ($params['language'] !== self::UNSET) {
            // Пустая строка с фронта = явный сброс на оригинал → передаём null,
            // а не пустую строку, чтобы совпасть с семантикой Python-стороны
            $data['language'] = $params['language'] === '' ? null : $params['language'];
        }

        if ($params['course_id'] !== self::UNSET_COURSE_ID) {
            // 0 = "All my courses" in the dropdown -> global mode (null on backend)
            $data['course_id'] = $params['course_id'] ?: null;
        }

        $service = new \local_ai_system\chatbot\service();

        $service->update_session(
            $params['session_id'],
            $data,
            $USER->id
        );

        return ['success' => true];
    }

    public static function update_session_returns() {
        return new external_single_structure([
            'success' => new external_value(PARAM_BOOL)
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
            'local/ai_system:use_chatbot',
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
            'local/ai_system:use_chatbot',
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
            'local/ai_system:use_chatbot',
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
            ),
            'cached_only' => new external_value(
                PARAM_BOOL,
                'Return at once; untranslated messages come back in the original with translation_pending',
                VALUE_DEFAULT,
                false
            ),
        ]);
    }

    // =========================
    // GET MESSAGES - MAIN LOGIC
    // =========================
    public static function get_messages(
        $session_id,
        $cached_only = false
    ) {

        $params = self::validate_parameters(
            self::get_messages_parameters(),
            [
                'session_id' => $session_id,
                'cached_only' => $cached_only,
            ]
        );

        $context = \context_system::instance();

        self::validate_context($context);

        require_capability(
            'local/ai_system:use_chatbot',
            $context
        );

        $service = new \local_ai_system\chatbot\service();

        global $USER;

        return $service->get_messages(
            $params['session_id'],
            $USER->id,
            (bool) $params['cached_only']
        );
    }

    // =========================
    // GET MESSAGES - RETURNS
    // =========================
    public static function get_messages_returns() {
        return new external_multiple_structure(self::message_structure());
    }

    /**
     * One chat message (get_messages, create_quiz).
     */
    private static function message_structure(int $required = VALUE_REQUIRED) {
        return new external_single_structure([

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

            'image_url' => new external_value(
                PARAM_URL,
                'URL to fetch the attached image, if any',
                VALUE_OPTIONAL
            ),

            'created_at' => new external_value(
                PARAM_TEXT,
                'Timestamp',
                VALUE_OPTIONAL
            ),

            'translation_pending' => new external_value(
                PARAM_BOOL,
                'Content is still the original; fetch the translation with local_ai_system_translate_message',
                VALUE_OPTIONAL
            ),

            'content_type' => new external_value(
                PARAM_ALPHANUMEXT,
                'text | quiz_request | quiz',
                VALUE_OPTIONAL
            ),

            'quiz_json' => new external_value(
                PARAM_RAW,
                'Quiz data as JSON (only for content_type quiz / quiz_request)',
                VALUE_OPTIONAL
            ),
        ], 'Message', $required);
    }

    // =========================
    // TRANSLATE ONE MESSAGE (progressive chat translation)
    // =========================
    public static function translate_message_parameters() {
        return new external_function_parameters([
            'session_id' => new external_value(PARAM_TEXT, 'Session ID'),
            'message_id' => new external_value(PARAM_INT, 'Message ID'),
        ]);
    }

    public static function translate_message($session_id, $message_id) {
        $params = self::validate_parameters(
            self::translate_message_parameters(),
            ['session_id' => $session_id, 'message_id' => $message_id]
        );

        $context = \context_system::instance();
        self::validate_context($context);
        require_capability('local/ai_system:use_chatbot', $context);

        global $USER;
        $service = new \local_ai_system\chatbot\service();
        $message = $service->translate_message($params['session_id'], (int) $params['message_id'], (int) $USER->id);

        return [
            'id'      => (int) ($message['id'] ?? $params['message_id']),
            'content' => (string) ($message['content'] ?? ''),
        ];
    }

    public static function translate_message_returns() {
        return new external_single_structure([
            'id'      => new external_value(PARAM_INT, 'Message ID'),
            'content' => new external_value(PARAM_RAW, 'Message text in the session language'),
        ]);
    }


    public static function save_partial_message_parameters() {
        return new external_function_parameters([
            'session_id' => new external_value(PARAM_TEXT, 'Session ID'),
            'content'    => new external_value(PARAM_RAW, 'Partially generated assistant text'),
        ]);
    }

    public static function save_partial_message($session_id, $content) {
        $params = self::validate_parameters(
            self::save_partial_message_parameters(),
            ['session_id' => $session_id, 'content' => $content]
        );

        $context = \context_system::instance();
        self::validate_context($context);
        require_capability('local/ai_system:use_chatbot', $context);

        $service = new \local_ai_system\chatbot\service();

        return $service->save_partial_message($params['session_id'], $params['content']);
    }

    public static function save_partial_message_returns() {
        return new external_single_structure([
            'id'      => new external_value(PARAM_INT, 'Message ID', VALUE_OPTIONAL),
            'role'    => new external_value(PARAM_TEXT, 'Role', VALUE_OPTIONAL),
            'content' => new external_value(PARAM_RAW, 'Content', VALUE_OPTIONAL),
        ]);
    }

    // =========================
    // QUIZ - CREATE
    // =========================
    public static function create_quiz_parameters() {
        return new external_function_parameters([
            'session_id' => new external_value(PARAM_TEXT, 'Session ID'),
            'scope'      => new external_value(PARAM_ALPHA, 'course = whole course, chat = this chat',
                                               VALUE_DEFAULT, 'course'),
            'count'      => new external_value(PARAM_INT, 'Number of questions (3, 5, 10, 20)', VALUE_DEFAULT, 5),
            'topic'      => new external_value(PARAM_TEXT, 'Optional topic', VALUE_DEFAULT, ''),
            'language'   => new external_value(PARAM_ALPHANUMEXT, 'Quiz language; empty = current Moodle language',
                                               VALUE_DEFAULT, ''),
        ]);
    }

    public static function create_quiz($session_id, $scope = 'course', $count = 5, $topic = '', $language = '') {
        global $USER;
        $params = self::validate_parameters(self::create_quiz_parameters(), [
            'session_id' => $session_id, 'scope' => $scope, 'count' => $count,
            'topic' => $topic, 'language' => $language,
        ]);

        $context = \context_system::instance();
        self::validate_context($context);
        require_capability('local/ai_system:use_chatbot', $context);

        $scope = $params['scope'] === 'chat' ? 'chat' : 'course';
        // "de", "en", "de_du" (informal German) -> "de"
        $language = $params['language'] !== '' ? $params['language'] : current_language();
        $language = strtolower(substr($language, 0, 2));

        $service = new \local_ai_system\chatbot\service();
        $response = $service->create_quiz(
            $params['session_id'], $scope, (int) $params['count'],
            trim($params['topic']), $language, (int) $USER->id
        );

        if ($error = self::quiz_error($response)) {
            return $error;
        }
        [$request, $quiz] = \local_ai_system\chatbot\service::normalise_messages(
            [$response['request'] ?? [], $response['quiz'] ?? []]
        );
        return [
            'request' => $request,
            'quiz'    => $quiz,
            'title'   => (string) ($response['title'] ?? ''),
        ];
    }

    public static function create_quiz_returns() {
        return new external_single_structure([
            'request'       => self::message_structure(VALUE_OPTIONAL),
            'quiz'          => self::message_structure(VALUE_OPTIONAL),
            'title'         => new external_value(PARAM_TEXT, 'New chat title (empty = unchanged)', VALUE_OPTIONAL),
            'error'         => new external_value(PARAM_ALPHANUMEXT, 'Error code', VALUE_OPTIONAL),
            'error_message' => new external_value(PARAM_TEXT, 'Error text from the backend', VALUE_OPTIONAL),
        ]);
    }

    // =========================
    // QUIZ - ANSWER ONE QUESTION
    // =========================
    public static function answer_quiz_parameters() {
        return new external_function_parameters([
            'session_id'     => new external_value(PARAM_TEXT, 'Session ID'),
            'message_id'     => new external_value(PARAM_INT, 'ID of the quiz message'),
            'question_index' => new external_value(PARAM_INT, 'Question number, 0-based'),
            'answer'         => new external_multiple_structure(
                new external_value(PARAM_INT, 'Index of a chosen option'),
                'Chosen option(s); one for single choice'
            ),
        ]);
    }

    public static function answer_quiz($session_id, $message_id, $question_index, $answer) {
        global $USER;
        $params = self::validate_parameters(self::answer_quiz_parameters(), [
            'session_id' => $session_id, 'message_id' => $message_id,
            'question_index' => $question_index, 'answer' => $answer,
        ]);

        $context = \context_system::instance();
        self::validate_context($context);
        require_capability('local/ai_system:use_chatbot', $context);

        $service = new \local_ai_system\chatbot\service();
        $response = $service->answer_quiz(
            $params['session_id'], (int) $params['message_id'],
            (int) $params['question_index'], $params['answer'], (int) $USER->id
        );

        if ($error = self::quiz_error($response)) {
            return $error;
        }
        return [
            'result_json' => json_encode($response['result'] ?? null, JSON_UNESCAPED_UNICODE),
            'quiz_json'   => json_encode($response['quiz'] ?? null, JSON_UNESCAPED_UNICODE),
        ];
    }

    public static function answer_quiz_returns() {
        return new external_single_structure([
            'result_json'   => new external_value(PARAM_RAW, 'The answered question (right option, explanation, source) as JSON', VALUE_OPTIONAL),
            'quiz_json'     => new external_value(PARAM_RAW, 'The whole quiz with all answers so far as JSON', VALUE_OPTIONAL),
            'error'         => new external_value(PARAM_ALPHANUMEXT, 'Error code', VALUE_OPTIONAL),
            'error_message' => new external_value(PARAM_TEXT, 'Error text from the backend', VALUE_OPTIONAL),
        ]);
    }

    /**
     * The backend answers quiz errors with {"detail": {"code", "message"}}
     * (or, for invalid input, {"detail": [ ...pydantic errors... ]}).
     * Returned as error/error_message so the JS can show a fitting text.
     */
    private static function quiz_error(array $response): ?array {
        if (!array_key_exists('detail', $response)) {
            return null;
        }
        $detail = $response['detail'];
        if (is_array($detail) && isset($detail['code'])) {
            return ['error' => (string) $detail['code'], 'error_message' => (string) ($detail['message'] ?? '')];
        }
        return ['error' => 'bad_request', 'error_message' => is_string($detail) ? $detail : 'Invalid request'];
    }
}
