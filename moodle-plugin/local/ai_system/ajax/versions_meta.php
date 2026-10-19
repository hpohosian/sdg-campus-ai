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
$url  = \local_ai_system\external\request_signer::base_url() . $path;

$payload = '{}';
// Signed headers (timestamp, signature, user id, enrolled courses): see
// classes/external/request_signer.php. The signature covers method, path,
// user, courses and body, so none of them can be changed on the way.
$headers = array_merge(
    ['Content-Type: application/json'],
    \local_ai_system\external\request_signer::headers('POST', $path, $payload, (int) $USER->id)
);

$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, $url);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);
curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);

$response = curl_exec($ch);

if (curl_errno($ch)) {
    http_response_code(500);
    header('Content-Type: application/json');
    echo json_encode(['error' => curl_error($ch)]);
    curl_close($ch);
    exit;
}

$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

http_response_code($http_code);
header('Content-Type: application/json');
echo $response;