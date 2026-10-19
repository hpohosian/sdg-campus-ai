<?php

namespace local_ai_system\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/filelib.php');

/**
 * Non-streaming HTTP client for the FastAPI backend.
 *
 * Authentication headers (signature, user id, enrolled courses) come from
 * request_signer, the same code the streaming ajax scripts use.
 */
class api_client {

    private string $internal_key;

    public function __construct() {
        $this->internal_key = (string) get_config('local_ai_system', 'internal_api_key');
    }

    /**
     * Debug log, only while Moodle's developer debugging is on. Request and
     * response bodies contain chat messages, so they must not be written
     * to a file on production systems.
     */
    private function log(string $message): void {
        global $CFG;

        if (!debugging('', DEBUG_DEVELOPER)) {
            return;
        }
        file_put_contents(
            $CFG->dirroot . '/debug.log',
            "[" . date('H:i:s') . "] " . $message . "\n",
            FILE_APPEND
        );
    }

    private function extractUserId(array $body): int {
        return (int)($body['user_id'] ?? $body['userid'] ?? 0);
    }

    private function request(string $method, string $path, array $body = [], int $user_id = 0, bool $internal = false): array {

        $method  = strtoupper($method);
        $url     = request_signer::base_url() . $path;
        $payload = !empty($body) ? json_encode($body, JSON_UNESCAPED_UNICODE) : '';
        $user_id = $user_id ?: $this->extractUserId($body);

        $this->log("METHOD: $method");
        $this->log("URL: $url");
        $this->log("BODY: " . $payload);

        // The signature covers exactly the $payload that is sent below.
        $headers = array_merge(
            ['Content-Type: application/json'],
            request_signer::headers($method, $path, $payload, $user_id)
        );

        if ($internal) {
            $headers[] = 'X-Internal-Api-Key: ' . $this->internal_key;
        }

        $curl = new \curl();
        $curl->ignore_security_hosts = true;
        $curl->setHeader($headers);

        switch ($method) {

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

    public function post_internal(string $path, array $body = [], int $user_id = 0): array {
        return $this->request('POST', $path, $body, $user_id, true);
    }
}
