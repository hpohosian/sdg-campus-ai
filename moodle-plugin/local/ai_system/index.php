<?php

require_once(__DIR__ . '/../../config.php');
require_login();

$context = context_system::instance();
require_capability('local/ai_system:use_chatbot', $context);

$PAGE->set_url(new moodle_url('/local/ai_system/index.php'));
$PAGE->set_context($context);
$PAGE->set_title('AI Chatbot');
$PAGE->set_heading('AI Chatbot');


// ==========================
// 1. Session ID (temporary)
// ==========================
$session_id = optional_param('session_id', null, PARAM_TEXT);

if (!$session_id) {
    $session_id = uniqid('chat_', true);
}

// ==========================
// 2. Load messages from service
// ==========================
$service = new \local_ai_system\chatbot\service();
$history = $service->get_history($USER->id, $session_id);

// ==========================
// 3. Render page
// ==========================
echo $OUTPUT->header();

// Mustache template data
$templatecontext = [
    'session_id' => $session_id,
    'messages'   => $history['messages'] ?? []
];

// Render chatbot UI
echo $OUTPUT->render_from_template('local_ai_system/chatbot', $templatecontext);

// ==========================
// 4. Load JS (AMD init)
// ==========================
$PAGE->requires->js_call_amd(
    'local_ai_system/chatbot',
    'init',
    [$session_id]
);

echo $OUTPUT->footer();