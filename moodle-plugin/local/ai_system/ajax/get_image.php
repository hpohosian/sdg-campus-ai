<?php

require_once(__DIR__ . '/../../../config.php');

require_login();
// No require_sesskey() here on purpose: this endpoint is opened by the browser
// as a plain <img src="..."> GET request, which cannot carry a sesskey (the
// URL is built by the backend). sesskey protects requests that CHANGE state
// (CSRF); this one only reads. Access is still protected by require_login(),
// the capability check below, and the backend, which returns the image only
// to the user who owns the session.

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
$path = "/sessions/{$session_id}/messages/{$message_id}/image";

// ==========================
// BODY + SIGNED HEADERS
// The body content itself is unused by the image endpoint; it exists only
// so the request has the same shape as every other authenticated request.
// ==========================
$payload = json_encode(['content' => '']);

// ==========================
// FETCH + RELAY (signed, through Moodle's curl wrapper: see classes/external/backend_http.php)
// ==========================
$result = \local_ai_system\external\backend_http::post($path, $payload, (int) $USER->id, 15);

if ($result['error'] !== '') {
    http_response_code(502);
    exit;
}
if ($result['code'] !== 200) {
    http_response_code($result['code'] ?: 502);
    exit;
}

$body = $result['body'];
header('Content-Type: ' . ($result['content_type'] ?: 'application/octet-stream'));
// Private cache: the browser (this user only) may cache it, shared/proxy
// caches must not — these are per-user chat attachments, not public assets.
header('Cache-Control: private, max-age=86400');
header('X-Content-Type-Options: nosniff');
header('Content-Length: ' . strlen($body));

echo $body;
