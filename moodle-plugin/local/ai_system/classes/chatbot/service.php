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
        string $session_id
    ): array {

        return $this->client->get(
            "/sessions/{$session_id}"
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
        int $userid
    ): array {

        $messages = $this->client->get(
            "/sessions/{$session_id}/messages",
            $userid
        );

        // Moodle's external API rejects `null` for VALUE_OPTIONAL fields —
        // the key must be entirely absent, not present-with-null.
        // FastAPI/pydantic always serializes "image_url": null for
        // messages with no attachment (rather than omitting the key), so
        // strip it here before it reaches chatbot_api.php's return-value
        // validation.
        foreach ($messages as &$message) {
            if (array_key_exists('image_url', $message) && $message['image_url'] === null) {
                unset($message['image_url']);
            }
        }
        unset($message);

        return $messages;
    }

    /**
     * Send message
     */
    public function send_message(
        string $session_id,
        string $message
    ): array {

        return $this->client->post(
            "/sessions/{$session_id}/messages",
            [
                'message' => $message
            ]
        );
    }


    /**
     * Persist a partially generated assistant response (after Stop)
     */
    public function save_partial_message(string $session_id, string $content): array {
        return $this->client->post(
            "/sessions/{$session_id}/messages/partial",
            ['content' => $content]
        );
    }
}
