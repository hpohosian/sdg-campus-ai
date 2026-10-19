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
$path = "/sessions/{$session_id}/messages/stream";
$url  = \local_ai_system\external\request_signer::base_url() . $path;

// ==========================
// BODY + SIGNED HEADERS
// ==========================
$payload_data = [
    'content' => $message,
];

if ($image_base64) {
    $payload_data['image_base64']    = $image_base64;
    $payload_data['image_mime_type'] = $image_mime_type;
}

$payload = json_encode($payload_data);

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
// Release the PHP session lock before the long-running stream. Otherwise every other
// request of this user (e.g. saving the partial answer after "Stop") has to wait until
// the whole stream has ended. Reading $USER stays possible afterwards.
\core\session\manager::write_close();

header('Content-Type: text/plain');
header('Cache-Control: no-cache');
header('Connection: keep-alive');

$ch = curl_init();

curl_setopt($ch, CURLOPT_URL, $url);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);

curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

// Pass the backend's HTTP status on to the browser (429 too many requests, 403 not enrolled,
// 401, 413, ...). Without this the browser would always see "200 OK" and an error body.
$status = 200;
$retry_after = null;
$head_sent = false;

curl_setopt($ch, CURLOPT_HEADERFUNCTION, function($curl, $line) use (&$status, &$retry_after) {
    if (preg_match('#^HTTP/\S+\s+(\d{3})#', $line, $m)) {
        $status = (int) $m[1];
        $retry_after = null;
    } else if (stripos($line, 'Retry-After:') === 0) {
        $retry_after = (int) trim(substr($line, 12));
    }
    return strlen($line);
});

curl_setopt($ch, CURLOPT_WRITEFUNCTION, function($curl, $data) use (&$status, &$retry_after, &$head_sent) {
    if (connection_aborted()) {
        return 0;
    }

    if (!$head_sent) {
        $head_sent = true;
        if ($status !== 200) {
            http_response_code($status);
            if ($retry_after) {
                header('Retry-After: ' . $retry_after);
            }
        }
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
