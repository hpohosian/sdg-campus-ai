<?php

require_once(__DIR__ . '/../../config.php');
require_login();

$plugin = new stdClass();
require($CFG->dirroot . '/local/ai_system/version.php');

$context = context_system::instance();
require_capability('local_ai_system:use_chatbot', $context);

$course_id = optional_param('course_id', 0, PARAM_INT);

$PAGE->set_url(new moodle_url('/local/ai_system/index.php'));
$PAGE->set_context($context);
$PAGE->set_title('AI Chatbot');
$PAGE->set_heading('AI Chatbot');

$PAGE->requires->css(new moodle_url('/local/ai_system/styles.css', ['v' => $plugin->version]));
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
$sessions = array_values($sessions);

// ==========================
// 1b. GET USER'S ENROLLED COURSES (for the course-picker dropdown)
// ==========================
$enrolled_courses = enrol_get_users_courses($USER->id, true, 'id, fullname');

$course_options = [];
foreach ($enrolled_courses as $course) {
    $course_options[] = [
        'id'       => $course->id,
        'fullname' => format_string($course->fullname),
        'selected' => ($course->id == $course_id) ? 1 : 0,
    ];
}

// ==========================
// 2. FIND ACTIVE SESSION
// ==========================
$current = null;
$session_id = null;
$history = ['messages' => []];

// ==========================
// 5. RENDER
// ==========================
echo $OUTPUT->header();

$active_sessions = array_filter($sessions, fn($s) => ($s['is_active'] ?? 1) == 1);
$archived_sessions = array_filter($sessions, fn($s) => ($s['is_active'] ?? 1) == 0);

$templatecontext = [
    'session_id' => $session_id ?? '',
    'messages'   => $history['messages'] ?? [],
    'sessions'   => array_values($active_sessions),
    'archived_sessions' => array_values($archived_sessions),
    'course_options' => $course_options,
    'has_courses' => count($course_options) > 0,
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
