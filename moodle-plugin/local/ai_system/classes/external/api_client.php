<?php

namespace local_ai_system\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/filelib.php');

class api_client {

    private string $base_url;
    private string $secret;

    public function __construct() {
        $this->base_url = 'http://127.0.0.1:8001';
        $this->secret   = get_config('local_ai_system', 'api_secret');
    }

    private function log(string $message): void {
        global $CFG;

        file_put_contents(
            $CFG->dirroot . '/debug.log',
            "[" . date('H:i:s') . "] " . $message . "\n",
            FILE_APPEND
        );
    }

    private function extractUserId(array $body): int {
        return (int)($body['user_id'] ?? $body['userid'] ?? 0);
    }

    private function request(string $method, string $path, array $body = [], int $user_id = 0): array {

        $url = $this->base_url . $path;

        $this->log("METHOD: $method");
        $this->log("URL: $url");
        $this->log("BODY: " . json_encode($body));

        $timestamp = time();
        $payload   = !empty($body)
            ? json_encode($body, JSON_UNESCAPED_UNICODE)
            : '';

        $signature = hash_hmac(
            'sha256',
            $timestamp . $payload,
            $this->secret
        );

        $curl = new \curl();
        $curl->ignore_security_hosts = true;

        $curl->setHeader([
            'Content-Type: application/json',
            'X-Timestamp: ' . $timestamp,
            'X-Signature: ' . $signature,
            'X-User-Id: ' . ($user_id ?: $this->extractUserId($body)),
        ]);

        switch (strtoupper($method)) {

            case 'GET':
                $response = $curl->get($url);
                break;

            case 'POST':
                $response = $curl->post($url, $payload);
                break;

            case 'PUT':
                $response = $curl->put($url, $payload);
                break;

            case 'DELETE':
                $response = $curl->delete($url, $payload);
                break;

            default:
                throw new \moodle_exception('Unsupported HTTP method');
        }

        $this->log("RAW RESPONSE: " . print_r($response, true));

        if ($curl->get_errno()) {
            $this->log("CURL ERROR: " . $curl->get_errno());
            throw new \moodle_exception('apierror', 'local_ai_system');
        }

        $decoded = json_decode($response, true);

        $this->log("DECODED: " . print_r($decoded, true));

        return is_array($decoded) ? $decoded : [];
    }

    public function get(string $path, int $user_id = 0): array {
        return $this->request('GET', $path, [], $user_id);
    }

    public function post(string $path, array $body = [], int $user_id = 0): array {
        return $this->request('POST', $path, $body, $user_id);
    }

    public function put(string $path, array $body = [], int $user_id = 0): array {
        return $this->request('PUT', $path, $body, $user_id);
    }

    public function delete(string $path, array $body = [], int $user_id = 0): array {
        return $this->request('DELETE', $path, $body, $user_id);
    }
}
