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
$content    = required_param('content', PARAM_RAW);

if (trim($content) === '') {
    http_response_code(400);
    echo 'Empty message.';
    exit;
}

global $USER;

// ==========================
// FASTAPI CONFIG
// ==========================
$path = "/sessions/{$session_id}/messages/{$message_id}/edit/stream";
$url  = \local_ai_system\external\request_signer::base_url() . $path;

// ==========================
// BODY + SIGNED HEADERS
// ==========================
$payload = json_encode(['content' => $content]);

// Signed headers (timestamp, signature, user id, enrolled courses): see
// classes/external/request_signer.php. The signature covers method, path,
// user, courses and body, so none of them can be changed on the way.
$headers = array_merge(
    ['Content-Type: application/json'],
    \local_ai_system\external\request_signer::headers('POST', $path, $payload, (int) $USER->id)
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

curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

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

curl_exec($ch);

if (curl_errno($ch)) {
    http_response_code(500);
    echo "Stream error: " . curl_error($ch);
}

curl_close($ch);