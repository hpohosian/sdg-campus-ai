<?php

require_once(__DIR__ . '/../../config.php');
require_login();

$context = context_system::instance();
require_capability('local_ai_system:use_chatbot', $context);

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
// 1. GET SESSIONS
// ==========================
$sessions = $service->get_sessions($USER->id);

// normalize array keys safety
$sessions = array_values($sessions);

// ==========================
// 2. FIND ACTIVE SESSION
// ==========================
$current = null;

foreach ($sessions as $s) {
    if (!empty($s['is_active']) && (int)$s['is_active'] === 1) {
        $current = $s;
        break;
    }
}

// ==========================
// 4. SAFE SESSION ID
// ==========================
$session_id = $current['session_id'] ?? null;


// ==========================
// 5. LOAD MESSAGES
// ==========================
$history = ['messages' => []];

if ($session_id) {
    $history = $service->get_messages($session_id);
}

// ==========================
// 6. RENDER
// ==========================
echo $OUTPUT->header();

$templatecontext = [
    'session_id' => $session_id ?? '',
    'messages'   => $history['messages'] ?? [],
    'sessions'   => $sessions
];

echo $OUTPUT->render_from_template(
    'local_ai_system/chatbot',
    $templatecontext
);

// ==========================
// 7. JS INIT
// ==========================
$PAGE->requires->js_call_amd(
    'local_ai_system/chatbot',
    'init',
    [$session_id]
);

echo $OUTPUT->footer();
