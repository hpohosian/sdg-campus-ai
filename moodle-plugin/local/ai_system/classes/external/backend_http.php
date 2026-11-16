<?php
// This file is part of Moodle - https://moodle.org/
//
// Moodle is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// Moodle is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with Moodle.  If not, see <https://www.gnu.org/licenses/>.

namespace local_ai_system\external;

defined('MOODLE_INTERNAL') || die();

require_once($CFG->libdir . '/filelib.php');

/**
 * All HTTP traffic to the FastAPI backend goes through Moodle's \curl class
 * (lib/filelib.php), not through PHP's curl_* functions.
 *
 * Why Moodle's wrapper: it applies the site's proxy settings
 * (Site administration > Server > HTTP), sends Moodle's user agent and is
 * the API the Moodle plugin guidelines ask for.
 *
 * Moodle's cURL security (blocked hosts / allowed ports) is switched off
 * for these requests on purpose: it protects against users making Moodle
 * fetch arbitrary URLs (SSRF). The backend URL here is not user input, it
 * is set by the admin in the plugin settings, and it normally IS a local
 * address such as http://127.0.0.1:8001, which the default security
 * settings would block (127.0.0.0/8 and port 8001 are not allowed).
 *
 * @package   local_ai_system
 */
class backend_http {

    /**
     * A Moodle curl object for one request to the backend.
     *
     * @return \curl
     */
    public static function new_curl(): \curl {
        $curl = new \curl(['ignoresecurity' => true]);
        // The backend never redirects. Moodle would follow a redirect by
        // sending the request again, which must not happen for a stream
        // whose first part already went to the browser.
        $curl->setopt(['CURLOPT_FOLLOWLOCATION' => 0]);
        return $curl;
    }

    /**
     * Signed request headers for one backend request (incl. Content-Type).
     *
     * @param string $method  HTTP method
     * @param string $path    backend path, e.g. /sessions/abc/messages/stream
     * @param string $payload the exact body that is sent
     * @param int    $userid  Moodle user id
     * @return string[]
     */
    public static function headers(string $method, string $path, string $payload, int $userid): array {
        return array_merge(
            ['Content-Type: application/json'],
            request_signer::headers($method, $path, $payload, $userid)
        );
    }

    /**
     * POST to the backend and return the whole answer.
     *
     * @param string $path    backend path
     * @param string $payload JSON body
     * @param int    $userid  Moodle user id
     * @param int    $timeout seconds, 0 = no limit
     * @return array ['code' => int, 'body' => string, 'content_type' => string, 'error' => string]
     *               'error' is '' unless the backend could not be reached at all.
     */
    public static function post(string $path, string $payload, int $userid, int $timeout = 0): array {
        $curl = self::new_curl();
        $curl->setHeader(self::headers('POST', $path, $payload, $userid));
        if ($timeout > 0) {
            $curl->setopt(['CURLOPT_TIMEOUT' => $timeout]);
        }

        $body = $curl->post(request_signer::base_url() . $path, $payload);
        $info = $curl->get_info();

        return [
            'code' => (int) ($info['http_code'] ?? 0),
            'body' => is_string($body) ? $body : '',
            'content_type' => (string) ($info['content_type'] ?? ''),
            'error' => $curl->get_errno() ? (string) $curl->error : '',
        ];
    }

    /**
     * POST to the backend and pass its answer to the browser piece by piece
     * as it arrives (the chat answer is streamed token by token).
     *
     * The backend's HTTP status is passed on too (429 too many requests,
     * 403 not enrolled, 413, ...), with Retry-After. Without that the
     * browser would always see "200 OK" with an error text as body.
     *
     * Call \core\session\manager::write_close() before: the stream can run
     * for a minute and must not block the user's other requests.
     *
     * @param string $path    backend path
     * @param string $payload JSON body
     * @param int    $userid  Moodle user id
     */
    public static function stream_post(string $path, string $payload, int $userid): void {
        $curl = self::new_curl();
        $curl->setHeader(self::headers('POST', $path, $payload, $userid));

        header('Content-Type: text/plain');
        header('Cache-Control: no-cache');
        header('X-Accel-Buffering: no'); // Nginx: do not buffer the stream.

        $retryafter = null;
        $headsent = false;

        $curl->setopt([
            // Only to read Retry-After. (This replaces Moodle's own header
            // parser for this request; we do not need its result.)
            'CURLOPT_HEADERFUNCTION' => function($ch, $line) use (&$retryafter) {
                if (preg_match('#^HTTP/\S+\s+\d{3}#', $line)) {
                    $retryafter = null; // A new response (e.g. after "100 Continue").
                } else if (stripos($line, 'Retry-After:') === 0) {
                    $retryafter = (int) trim(substr($line, 12));
                }
                return strlen($line);
            },
            // Every piece of the answer goes straight to the browser.
            'CURLOPT_WRITEFUNCTION' => function($ch, $data) use (&$retryafter, &$headsent) {
                if (connection_aborted()) {
                    return 0; // The user pressed "Stop": cancel the backend request.
                }
                if (!$headsent) {
                    $headsent = true;
                    $status = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
                    if ($status && $status !== 200) {
                        http_response_code($status);
                        if ($retryafter) {
                            header('Retry-After: ' . $retryafter);
                        }
                    }
                }
                echo $data;
                if (ob_get_level() > 0) {
                    ob_flush();
                }
                flush();
                return strlen($data);
            },
            'CURLOPT_TIMEOUT' => 0,
        ]);

        $curl->post(request_signer::base_url() . $path, $payload);

        // Errno 23 (write error) is our own "return 0" after the user stopped.
        if ($curl->get_errno() && $curl->get_errno() !== CURLE_WRITE_ERROR && !$headsent) {
            http_response_code(502);
            echo 'Stream error: ' . $curl->error;
        }
    }

    /**
     * POST to the backend and send its JSON answer on unchanged
     * (same HTTP status). For the small ajax/*.php endpoints.
     *
     * @param string $path    backend path
     * @param string $payload JSON body
     * @param int    $userid  Moodle user id
     */
    public static function relay_json(string $path, string $payload, int $userid): void {
        $result = self::post($path, $payload, $userid);

        header('Content-Type: application/json');
        if ($result['error'] !== '') {
            http_response_code(502);
            echo json_encode(['error' => $result['error']]);
            return;
        }
        http_response_code($result['code'] ?: 502);
        echo $result['body'];
    }
}
