<?php

namespace local_ai_system\chatbot;

defined('MOODLE_INTERNAL') || die();

use local_ai_system\external\api_client;

class service {

    private api_client $client;

    public function __construct() {
        $this->client = new api_client();
    }

    // =========================
    // SESSIONS
    // =========================

    /**
     * Create session
     */
    public function create_session(int $userid, string $title = 'New Chat', int $course_id = 0): array {

        return $this->client->post(
            '/sessions',
            [
                'user_id'   => $userid,
                'title'     => $title,
                'course_id' => $course_id ?: null
            ],
            $userid
        );
    }

    /**
     * Get all user sessions
     */
    public function get_sessions(int $userid): array {

        return $this->client->get(
            '/sessions',
            $userid
        );
    }

    /**
     * Get single session
     */
    public function get_session(
        string $session_id,
        int $userid = 0
    ): array {

        return $this->client->get(
            "/sessions/{$session_id}",
            self::user_or_current($userid)
        );
    }

    /**
     * Update session
     */
    public function update_session(
        string $session_id,
        array $data,
        int $userid
    ): array {

        return $this->client->put(
            "/sessions/{$session_id}",
            $data,
            $userid
        );
    }

    /**
     * Delete session
     */
    public function delete_session(
        string $session_id,
        int $userid
    ): array {

        return $this->client->delete(
            "/sessions/{$session_id}",
            [],
            $userid
        );
    }

    /**
     * Archive session
     */
    public function archive_session(
        string $session_id,
        int $userid
    ): array {

        return $this->client->put(
            "/sessions/archive/{$session_id}",
            [],
            $userid
        );
    }

    /**
     * Dearchive session
     */
    public function dearchive_session(
        string $session_id,
        int $userid
    ): array {

        return $this->client->put(
            "/sessions/dearchive/{$session_id}",
            [],
            $userid
        );
    }

    // =========================
    // MESSAGES
    // =========================

    /**
     * Get session messages
     */
    public function get_messages(
        string $session_id,
        int $userid,
        bool $cached_only = false
    ): array {

        // cached_only: the backend answers at once and marks messages that
        // still need translating (translation_pending) instead of translating
        // the whole chat first. The query string is not part of the request
        // signature, it only switches this behaviour.
        $query = $cached_only ? '?cached_only=true' : '';

        $messages = $this->client->get(
            "/sessions/{$session_id}/messages{$query}",
            $userid
        );

        return self::normalise_messages($messages);
    }

    /**
     * One message translated into the session's current language.
     */
    public function translate_message(string $session_id, int $message_id, int $userid = 0): array {
        $message = $this->client->post(
            "/sessions/{$session_id}/messages/{$message_id}/translate",
            [],
            self::user_or_current($userid)
        );
        return self::strip_null_image_urls([$message])[0];
    }

    /**
     * Moodle's external API rejects `null` for VALUE_OPTIONAL fields —
     * the key must be entirely absent, not present-with-null.
     * FastAPI/pydantic always serializes "image_url": null for
     * messages with no attachment (rather than omitting the key), so
     * strip it here before it reaches chatbot_api.php's return-value
     * validation. Pulled out as its own method so it's testable
     * without a live backend.
     */
    public static function strip_null_image_urls(array $messages): array {
        foreach ($messages as &$message) {
            if (array_key_exists('image_url', $message) && $message['image_url'] === null) {
                unset($message['image_url']);
            }
        }
        unset($message);

        return $messages;
    }

    /**
     * Messages as chatbot_api's return structure expects them:
     *  - no "image_url": null (see strip_null_image_urls),
     *  - quiz messages (content_type "quiz" / "quiz_request"): the nested
     *    "quiz" object becomes the JSON string "quiz_json". The quiz data is
     *    nested and grows with new question types; as a string it does not
     *    need a Moodle return structure for every field (the JS parses it).
     */
    public static function normalise_messages(array $messages): array {
        $messages = self::strip_null_image_urls($messages);
        foreach ($messages as &$message) {
            if (array_key_exists('quiz', $message)) {
                if ($message['quiz'] !== null) {
                    $message['quiz_json'] = json_encode($message['quiz'], JSON_UNESCAPED_UNICODE);
                }
                unset($message['quiz']);
            }
            if (empty($message['content_type'])) {
                $message['content_type'] = 'text';
            }
        }
        unset($message);
        return $messages;
    }

    // =========================
    // QUIZ (self-study; see api/chatbot/quiz/service.py)
    // =========================

    /**
     * Generates a quiz (10-30 s) and appends it to the chat.
     * Returns the backend answer: {"request", "quiz", "title"} or,
     * on an error, {"detail": {"code", "message"}}.
     */
    public function create_quiz(
        string $session_id,
        string $scope,
        int $count,
        string $topic,
        string $language,
        int $userid = 0
    ): array {
        return $this->client->post(
            "/sessions/{$session_id}/quiz",
            [
                'scope'    => $scope,
                'count'    => $count,
                'topic'    => $topic !== '' ? $topic : null,
                'language' => $language !== '' ? $language : null,
            ],
            self::user_or_current($userid)
        );
    }

    /**
     * Answers one question; the backend checks it.
     * Returns {"question_index", "result", "quiz"} or {"detail": {...}}.
     */
    public function answer_quiz(
        string $session_id,
        int $message_id,
        int $question_index,
        array $answer,
        int $userid = 0
    ): array {
        return $this->client->post(
            "/sessions/{$session_id}/quiz/{$message_id}/answer",
            [
                'question_index' => $question_index,
                'answer'         => array_values(array_map('intval', $answer)),
            ],
            self::user_or_current($userid)
        );
    }

    /**
     * Send message
     */
    public function send_message(
        string $session_id,
        string $message,
        int $userid = 0
    ): array {

        return $this->client->post(
            "/sessions/{$session_id}/messages",
            [
                'message' => $message
            ],
            self::user_or_current($userid)
        );
    }


    /**
     * Persist a partially generated assistant response (after Stop)
     */
    public function save_partial_message(string $session_id, string $content, int $userid = 0): array {
        return $this->client->post(
            "/sessions/{$session_id}/messages/partial",
            ['content' => $content],
            self::user_or_current($userid)
        );
    }

    /**
     * The backend needs to know whose request this is (it is part of the signature).
     * Callers that do not pass a user id are acting for the logged-in user.
     */
    private static function user_or_current(int $userid): int {
        global $USER;
        return $userid > 0 ? $userid : (int) $USER->id;
    }
}
