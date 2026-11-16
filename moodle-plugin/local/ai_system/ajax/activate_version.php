<?php

require_once(__DIR__ . '/../../../config.php');

require_login();
require_sesskey();

$context = context_system::instance();
require_capability('local/ai_system:use_chatbot', $context);

// PARAM_ALPHANUMEXT (letters, digits, _ and -): the value is put into the URL
// path sent to the backend, so slashes and dots must not get through.
$session_id = required_param('session_id', PARAM_ALPHANUMEXT);
$message_id = required_param('message_id', PARAM_INT);

global $USER;

$path = "/sessions/{$session_id}/messages/{$message_id}/activate";

$payload = '{}';
// Signed headers + Moodle's curl wrapper: see classes/external/backend_http.php.
\local_ai_system\external\backend_http::relay_json($path, $payload, (int) $USER->id);
