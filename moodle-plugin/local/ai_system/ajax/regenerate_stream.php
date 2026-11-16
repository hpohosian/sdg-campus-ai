<?php

require_once(__DIR__ . '/../../../config.php');

require_login();
require_sesskey();

$context = context_system::instance();
require_capability('local/ai_system:use_chatbot', $context);

// ==========================
// INPUT
// ==========================
// PARAM_ALPHANUMEXT (letters, digits, _ and -): the value is put into the URL
// path sent to the backend, so slashes and dots must not get through.
$session_id = required_param('session_id', PARAM_ALPHANUMEXT);
$message_id = required_param('message_id', PARAM_INT);

global $USER;

// ==========================
// FASTAPI CONFIG
// ==========================
$path = "/sessions/{$session_id}/messages/{$message_id}/regenerate/stream";

// ==========================
// BODY (none needed, so "{}") + SIGNED HEADERS
// ==========================
$payload = '{}';

// Signed headers + Moodle's curl wrapper: see classes/external/backend_http.php.
// Release the PHP session lock before the long-running stream. Otherwise every other
// request of this user (e.g. saving the partial answer after "Stop") has to wait until
// the whole stream has ended. Reading $USER stays possible afterwards.
\core\session\manager::write_close();

\local_ai_system\external\backend_http::stream_post($path, $payload, (int) $USER->id);
