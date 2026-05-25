<?php

require_once(__DIR__ . '/../../../config.php');
require_login();

header('Content-Type: application/json');

$context = context_system::instance();
require_capability('local_ai_system:use_chatbot', $context);

$service = new \local_ai_system\chatbot\service();

$title = optional_param('title', 'New Chat', PARAM_TEXT);
$session = $service->create_session($USER->id, $title);

echo json_encode([
    'session_id' => $session['session_id']
]);