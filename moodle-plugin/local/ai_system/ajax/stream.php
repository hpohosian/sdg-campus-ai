<?php

require_once(__DIR__ . '/../../../config.php');

require_login();

$context = context_system::instance();
require_capability('local_ai_system:use_chatbot', $context);

// ==========================
// INPUT
// ==========================
$session_id = required_param('session_id', PARAM_TEXT);
$message    = required_param('message', PARAM_RAW);

// ==========================
// SECURITY CHECK
// ==========================
global $USER;

// ==========================
// FASTAPI CONFIG
// ==========================
$base_url = 'http://127.0.0.1:8001';

$url = $base_url . "/sessions/{$session_id}/messages/stream";

// ==========================
// SIGNATURE (same logic as api_client)
// ==========================
$timestamp = time();

$secret = get_config('local_ai_system', 'api_secret');

$payload = json_encode([
    'content' => $message,
]);

$signature = hash_hmac(
    'sha256',
    $timestamp . $payload,
    $secret
);

// ==========================
// CURL STREAM
// ==========================
header('Content-Type: text/plain');
header('Cache-Control: no-cache');
header('Connection: keep-alive');

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

curl_setopt($ch, CURLOPT_WRITEFUNCTION, function($curl, $data) {
    if (connection_aborted()) {
        return 0;
    }

    echo $data;
    ob_flush();
    flush();
    return strlen($data);
});

curl_setopt($ch, CURLOPT_TIMEOUT, 0);
curl_setopt($ch, CURLOPT_BUFFERSIZE, 1);

// IMPORTANT: stream mode
curl_exec($ch);

if (curl_errno($ch)) {
    http_response_code(500);
    echo "Stream error: " . curl_error($ch);
}

curl_close($ch);
