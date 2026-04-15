<?php

namespace local_ai_system\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/filelib.php');

class api_client {

    private string $base_url;
    private string $secret;

    public function __construct() {
        // $this->base_url = get_config('local_ai_system', 'api_url');
        $this->base_url = 'http://127.0.0.1:8001';
        $this->secret   = get_config('local_ai_system', 'api_secret');
    }

    private function log($message) {
        global $CFG;
        file_put_contents(
            $CFG->dirroot . '/debug.log',
            "[" . date('H:i:s') . "] " . $message . "\n",
            FILE_APPEND
        );
    }

    public function post(string $path, array $body): array {

        $this->log("API CLIENT CALLED");

        if (empty($this->base_url)) {
            $this->log("ERROR: API URL IS EMPTY");
        }

        $this->log("BASE URL: " . $this->base_url);
        $this->log("FULL URL: " . $this->base_url . $path);
        $this->log("REQUEST BODY: " . json_encode($body));

        $timestamp = time();

        $signature = hash_hmac(
            'sha256',
            $timestamp . json_encode($body),
            $this->secret
        );

        $this->log("TIMESTAMP: " . $timestamp);
        $this->log("SIGNATURE GENERATED");

        $curl = new \curl();

        $curl->ignore_security_hosts = true;

        $curl->setHeader([
            'Content-Type: application/json',
            'X-Timestamp: ' . $timestamp,
            'X-Signature: ' . $signature,
        ]);

       $response = $curl->post(
            $this->base_url . $path,
            json_encode($body),
            [
                'timeout' => 30,
                'CURLOPT_CONNECTTIMEOUT' => 10
            ]
        );

        $this->log("CURL RESPONSE RAW: " . print_r($response, true));

        if ($curl->get_errno()) {
            $this->log("CURL ERROR: " . $curl->get_errno());
            throw new \moodle_exception('apierror', 'local_ai_system');
        }

        $decoded = json_decode($response, true);

        $this->log("DECODED RESPONSE: " . print_r($decoded, true));

        return is_array($decoded) ? $decoded : [];
    }
}
