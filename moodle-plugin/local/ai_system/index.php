<?php

require_once(__DIR__ . '/../../config.php');
require_login();

$context = context_system::instance();
require_capability('local_ai_system:use_chatbot', $context);

$course_id = optional_param('course_id', 0, PARAM_INT);

$PAGE->set_url(new moodle_url('/local/ai_system/index.php'));
$PAGE->set_context($context);
$PAGE->set_title('AI Chatbot');
$PAGE->set_heading('AI Chatbot');

$PAGE->requires->css(new moodle_url('/local/ai_system/styles.css'));
$PAGE->requires->js(
    new moodle_url('https://cdn.jsdelivr.net/npm/marked/marked.min.js'),
    true
);

$embed = optional_param('embed', 0, PARAM_INT);

if ($embed) {
    $PAGE->set_pagelayout('embedded');
}

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

// ==========================
// 3. SAFE SESSION ID
// ==========================
$session_id = null;


// ==========================
// 4. LOAD MESSAGES
// ==========================
$history = ['messages' => []];

// ==========================
// 5. RENDER
// ==========================
echo $OUTPUT->header();

$active_sessions = array_filter($sessions, fn($s) => ($s['is_active'] ?? 1) == 1);
$archived_sessions = array_filter($sessions, fn($s) => ($s['is_active'] ?? 1) == 0);

// var_dump($sessions);
// exit();

$templatecontext = [
    'session_id' => $session_id ?? '',
    'messages'   => $history['messages'] ?? [],
    'sessions'   => array_values($active_sessions),
    'archived_sessions' => array_values($archived_sessions),
];

echo $OUTPUT->render_from_template(
    'local_ai_system/chatbot',
    $templatecontext
);

// ==========================
// 6. JS INIT
// ==========================
$PAGE->requires->js_call_amd(
    'local_ai_system/chatbot',
    'init',
    [$session_id, $course_id]
);

echo $OUTPUT->footer();
