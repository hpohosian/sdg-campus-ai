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
$url  = \local_ai_system\external\request_signer::base_url() . $path;

// ==========================
// BODY + SIGNED HEADERS
// The body content itself is unused by the image endpoint; it exists only
// so the request has the same shape as every other authenticated request.
// ==========================
$payload = json_encode(['content' => '']);

// Signed headers (timestamp, signature, user id, enrolled courses): see
// classes/external/request_signer.php. The signature covers method, path,
// user, courses and body, so none of them can be changed on the way.
$headers = array_merge(
    ['Content-Type: application/json'],
    \local_ai_system\external\request_signer::headers('POST', $path, $payload, (int) $USER->id)
);

// ==========================
// FETCH + RELAY
// ==========================
$ch = curl_init();

curl_setopt($ch, CURLOPT_URL, $url);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);
curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HEADER, true);
curl_setopt($ch, CURLOPT_TIMEOUT, 15);

$response = curl_exec($ch);

if (curl_errno($ch)) {
    http_response_code(502);
    curl_close($ch);
    exit;
}

$header_size  = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$http_code    = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$content_type = curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
curl_close($ch);

$body = substr($response, $header_size);

if ($http_code !== 200) {
    http_response_code($http_code ?: 502);
    exit;
}

header('Content-Type: ' . ($content_type ?: 'application/octet-stream'));
// Private cache: the browser (this user only) may cache it, shared/proxy
// caches must not — these are per-user chat attachments, not public assets.
header('Cache-Control: private, max-age=86400');
header('X-Content-Type-Options: nosniff');
header('Content-Length: ' . strlen($body));

echo $body;
