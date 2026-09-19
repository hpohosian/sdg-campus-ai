<?php

require_once(__DIR__ . '/../../../config.php');

require_login();
require_sesskey();

$context = context_system::instance();
require_capability('local/ai_system:use_chatbot', $context);

// ==========================
// INPUT
// ==========================
$session_id = required_param('session_id', PARAM_TEXT);
$message_id = required_param('message_id', PARAM_INT);

global $USER;

// ==========================
// FASTAPI CONFIG
// ==========================
$base_url = 'http://127.0.0.1:8001';
$url = $base_url . "/sessions/{$session_id}/messages/{$message_id}/image";

// ==========================
// SIGNATURE (same scheme as stream.php — HMAC over timestamp + JSON body).
// The body content itself is unused by the image endpoint; it exists only
// so the signature check has the same shape as every other authenticated
// request in this plugin.
// ==========================
$timestamp = time();
$secret = get_config('local_ai_system', 'api_secret');
$payload = json_encode(['content' => '']);
$signature = hash_hmac('sha256', $timestamp . $payload, $secret);

// ==========================
// FETCH + RELAY
// ==========================
$ch = curl_init();

curl_setopt($ch, CURLOPT_URL, $url);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Content-Type: application/json',
    'X-Timestamp: ' . $timestamp,
    'X-Signature: ' . $signature,
    'X-User-Id: ' . $USER->id,
]);
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
header('Content-Length: ' . strlen($body));

echo $body;
