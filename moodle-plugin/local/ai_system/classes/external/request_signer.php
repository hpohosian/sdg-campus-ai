<?php

namespace local_ai_system\external;

defined('MOODLE_INTERNAL') || die();

/**
 * Builds the signed request headers for the FastAPI backend.
 *
 * ONE place for everything that authenticates a request to the backend, so
 * the ajax scripts (stream.php, ...) and api_client no longer each carry their
 * own copy of the signing code.
 *
 * The signature covers what the backend trusts: timestamp, HTTP method, path,
 * user id, the list of courses the user is enrolled in, and the request body:
 *
 *   HMAC-SHA256(secret, "v2\n" . timestamp . "\n" . METHOD . "\n" . path . "\n"
 *                       . user_id . "\n" . enrolled_courses . "\n" . sha256(body))
 *
 * It must match api/middleware/auth.py (compute_signature) exactly.
 */
class request_signer {

    const VERSION = 'v2';

    /** Upper limits so the X-Enrolled-Courses header stays a sane size. */
    const MAX_COURSES = 200;
    const MAX_NAME_LENGTH = 100;

    /** Base URL of the backend, e.g. http://127.0.0.1:8001 (no trailing slash). */
    public static function base_url(): string {
        $url = get_config('local_ai_system', 'api_base_url') ?: 'http://127.0.0.1:8001';
        return rtrim($url, '/');
    }

    /** The shared secret. Fails loudly instead of silently signing with an empty key. */
    private static function secret(): string {
        $secret = (string) get_config('local_ai_system', 'api_secret');
        if ($secret === '') {
            throw new \moodle_exception('apierror', 'local_ai_system', '', null, 'api_secret is not configured');
        }
        return $secret;
    }

    /** Path part of a path or URL, without query string (the signature never covers the query). */
    public static function path_of(string $path_or_url): string {
        $path = parse_url($path_or_url, PHP_URL_PATH);
        return ($path === null || $path === false || $path === '') ? '/' : $path;
    }

    /**
     * [course id => name] -> base64url(JSON object). Empty list -> ''.
     * Pure function (no Moodle calls), so it can be tested on its own.
     */
    public static function encode_courses(array $courses): string {
        if (empty($courses)) {
            return '';
        }
        $json = json_encode((object) $courses, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
        return rtrim(strtr(base64_encode($json), '+/', '-_'), '=');
    }

    /** The courses the user is actively enrolled in, encoded for the X-Enrolled-Courses header. */
    public static function enrolled_courses_value(int $user_id): string {
        global $CFG;
        require_once($CFG->libdir . '/enrollib.php');

        $courses = [];
        foreach (enrol_get_users_courses($user_id, true, 'id, fullname') as $course) {
            if (count($courses) >= self::MAX_COURSES) {
                debugging('local_ai_system: more than ' . self::MAX_COURSES .
                    ' enrolled courses, the rest is not sent to the backend', DEBUG_DEVELOPER);
                break;
            }
            // 'escape' => false: plain text for the markdown link in the answer, no HTML entities.
            $name = strip_tags(format_string($course->fullname, true, ['escape' => false]));
            $courses[(int) $course->id] = \core_text::substr($name, 0, self::MAX_NAME_LENGTH);
        }
        return self::encode_courses($courses);
    }

    /** Pure function, see class comment. */
    public static function compute_signature(
        string $secret,
        string $timestamp,
        string $method,
        string $path,
        string $user_id,
        string $courses,
        string $body
    ): string {
        $message = implode("\n", [
            self::VERSION,
            $timestamp,
            strtoupper($method),
            $path,
            $user_id,
            $courses,
            hash('sha256', $body),
        ]);
        return hash_hmac('sha256', $message, $secret);
    }

    /**
     * Header lines for one request to the backend.
     *
     * @param string $method  HTTP method
     * @param string $path    path (or URL) being requested
     * @param string $body    the exact body that will be sent ('' if none)
     * @param int    $user_id Moodle user id; 0 = system call (no enrolled courses are sent)
     * @return string[] lines like 'X-Signature: ...' (Content-Type is left to the caller)
     */
    public static function headers(string $method, string $path, string $body, int $user_id): array {
        $timestamp = (string) time();
        $courses = $user_id > 0 ? self::enrolled_courses_value($user_id) : '';

        $signature = self::compute_signature(
            self::secret(),
            $timestamp,
            $method,
            self::path_of($path),
            (string) $user_id,
            $courses,
            $body
        );

        $headers = [
            'X-Timestamp: ' . $timestamp,
            'X-Signature: ' . $signature,
            'X-User-Id: ' . $user_id,
        ];
        if ($courses !== '') {
            $headers[] = 'X-Enrolled-Courses: ' . $courses;
        }
        return $headers;
    }
}
