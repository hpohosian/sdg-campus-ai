<?php

require_once(__DIR__ . '/../../../config.php');

require_login();

$context = context_system::instance();
require_capability('local_ai_system:use_chatbot', $context);

// ==========================
// INPUT
// ==========================
$session_id = required_param('session_id', PARAM_TEXT);
// Text is now optional — the user may send an image with no question.
$message    = optional_param('message', '', PARAM_RAW);

// ==========================
// OPTIONAL IMAGE ATTACHMENT
// ==========================
define('MAX_IMAGE_BYTES', 8 * 1024 * 1024); // 8 MB
define('ALLOWED_IMAGE_MIMES', ['image/jpeg', 'image/png', 'image/webp', 'image/gif']);

$image_base64    = null;
$image_mime_type = null;

if (!empty($_FILES['image']) && $_FILES['image']['error'] !== UPLOAD_ERR_NO_FILE) {

    if ($_FILES['image']['error'] !== UPLOAD_ERR_OK) {
        http_response_code(400);
        echo 'Image upload failed.';
        exit;
    }

    if ($_FILES['image']['size'] > MAX_IMAGE_BYTES) {
        http_response_code(413);
        echo 'Image too large (max 8 MB).';
        exit;
    }

    // Trust the actual file bytes over the client-supplied MIME type.
    $finfo = finfo_open(FILEINFO_MIME_TYPE);
    $detected_mime = finfo_file($finfo, $_FILES['image']['tmp_name']);
    finfo_close($finfo);

    if (!in_array($detected_mime, ALLOWED_IMAGE_MIMES, true)) {
        http_response_code(415);
        echo 'Unsupported image type. Allowed: JPEG, PNG, WEBP, GIF.';
        exit;
    }

    $image_mime_type = $detected_mime;
    $image_base64 = base64_encode(file_get_contents($_FILES['image']['tmp_name']));
}

if ($message === '' && !$image_base64) {
    http_response_code(400);
    echo 'Empty message.';
    exit;
}

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

$payload_data = [
    'content' => $message,
];

if ($image_base64) {
    $payload_data['image_base64']    = $image_base64;
    $payload_data['image_mime_type'] = $image_mime_type;
}

$payload = json_encode($payload_data);

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
