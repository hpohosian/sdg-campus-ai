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
$url  = \local_ai_system\external\request_signer::base_url() . $path;

// ==========================
// BODY (none needed, so "{}") + SIGNED HEADERS
// ==========================
$payload = '{}';

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

curl_exec($ch);

if (curl_errno($ch)) {
    http_response_code(500);
    echo "Stream error: " . curl_error($ch);
}

curl_close($ch);