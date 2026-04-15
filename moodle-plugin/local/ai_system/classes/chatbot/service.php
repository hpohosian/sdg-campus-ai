<?php

namespace local_ai_system\chatbot;

defined('MOODLE_INTERNAL') || die();

use local_ai_system\external\api_client;

class service {

    /**
     * Send message to AI and return response
     */
    public function send_message(int $userid, string $session_id, string $message): array {

        global $DB;

        $time = time();

        // =========================
        // 1. Save USER message
        // =========================
        $userMessage = (object)[
            'session_id'   => $session_id,
            'role'         => 'user',
            'content'      => $message,
            'created_at'   => $time
        ];

        $DB->insert_record('local_ai_system_messages', $userMessage);

        // =========================
        // 2. Call FastAPI
        // =========================
        $client = new api_client();

        $response = $client->post('/chat', [
            'session_id' => $session_id,
            'user_id'    => $userid,
            'message'    => $message
        ]);

        error_log("AI REQUEST: " . json_encode([
            'session_id' => $session_id,
            'message' => $message,
            'user_id' => $userid
        ]));

        error_log("AI RESPONSE: " . json_encode($response));

        // =========================
        // 3. Extract AI response
        // =========================
        $aiMessageText = $response['message'] ?? 'No response';

        // =========================
        // 4. Save AI message
        // =========================
        $aiMessage = (object)[
            'session_id'   => $session_id,
            'role'         => 'assistant',
            'content'      => $aiMessageText,
            'created_at'   => time()
        ];

        $DB->insert_record('local_ai_system_messages', $aiMessage);

        // =========================
        // 5. Return to frontend
        // =========================
        return [
            'message' => $aiMessageText,
            'session_id' => $session_id
        ];
    }


    /**
     * Get chat history
     */
    public function get_history(int $userid, string $session_id): array {

        global $DB;

        $messages = $DB->get_records('local_ai_system_messages', [
            'session_id' => $session_id
        ], 'created_at ASC');

        $result = [];

        foreach ($messages as $msg) {
            $result[] = [
                'role' => $msg->role,
                'content' => $msg->content,
                'created_at' => date('H:i', $msg->created_at)
            ];
        }

        return [
            'session_id' => $session_id,
            'messages'   => $result
        ];
    }
}
