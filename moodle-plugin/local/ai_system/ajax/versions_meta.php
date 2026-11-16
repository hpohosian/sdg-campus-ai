<?php

require_once(__DIR__ . '/../../../config.php');

require_login();
require_sesskey();

$context = context_system::instance();
require_capability('local/ai_system:use_chatbot', $context);

// PARAM_ALPHANUMEXT (letters, digits, _ and -): the value is put into the URL
// path sent to the backend, so slashes and dots must not get through.
$session_id = required_param('session_id', PARAM_ALPHANUMEXT);

global $USER;

$path = "/sessions/{$session_id}/messages-versions-meta";

$payload = '{}';
// Signed headers + Moodle's curl wrapper: see classes/external/backend_http.php.
\local_ai_system\external\backend_http::relay_json($path, $payload, (int) $USER->id);
