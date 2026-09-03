<?php

require_once(__DIR__ . '/../../../config.php');

require_login();

$context = context_system::instance();
require_capability('local_ai_system:use_chatbot', $context);

$session_id = required_param('session_id', PARAM_TEXT);

global $USER;

$base_url = 'http://127.0.0.1:8001';
$url = $base_url . "/sessions/{$session_id}/messages-versions-meta";

$timestamp = time();
$secret = get_config('local_ai_system', 'api_secret');
$payload = '{}';
$signature = hash_hmac('sha256', $timestamp . $payload, $secret);

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