<?php

require_once(__DIR__ . '/../../config.php');
require_login();

$context = context_system::instance();
require_capability('local/ai_system:use_chatbot', $context);

$PAGE->set_url(new moodle_url('/local/ai_system/index.php'));
$PAGE->set_context($context);
$PAGE->set_title('AI Chatbot');
$PAGE->set_heading('AI Chatbot');
$PAGE->requires->css(new moodle_url('/local/ai_system/styles.css'));
$PAGE->requires->js(
    new moodle_url('https://cdn.jsdelivr.net/npm/marked/marked.min.js'),
    true
);

$service = new \local_ai_system\chatbot\service();

// ==========================
// 1. Sessions
// ==========================

// Get all sessions
$sessions = $service->get_sessions($USER->id);

// 2. If there are no sessions, create the first one
if (empty($sessions)) {
    $current = $service->create_session($USER->id);
    $session_id = $current['session_id'];
} else {
    // $current = reset($sessions);
    $current = null;

    foreach ($sessions as $s) {
        if ($s['is_active'] ?? false) {
            $current = $s;
            break;
        }
    }

    if (!$current) {
        $current = $service->create_session($USER->id);
        $session_id = $current['session_id'];
    } else {
        $session_id = $current['session_id'];
    }
}

// ==========================
// 2. Load messages from service
// ==========================
if (empty($session_id)) {
    $session_id = $current['session_id'];
}
$history = $service->get_history($USER->id, $session_id);

// ==========================
// 3. Render page
// ==========================
echo $OUTPUT->header();

// Mustache template data
$templatecontext = [
    'session_id' => $session_id,
    'messages'   => $history['messages'] ?? [],
    'sessions'   => array_values($sessions)
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