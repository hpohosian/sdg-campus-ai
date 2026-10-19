<?php

namespace local_ai_system\privacy;

use core_privacy\local\metadata\collection;
use core_privacy\local\request\approved_contextlist;
use core_privacy\local\request\approved_userlist;
use core_privacy\local\request\contextlist;
use core_privacy\local\request\core_userlist_provider;
use core_privacy\local\request\transform;
use core_privacy\local\request\userlist;
use core_privacy\local\request\writer;
use local_ai_system\external\api_client;

defined('MOODLE_INTERNAL') || die();

/**
 * Privacy API (GDPR) for local_ai_system.
 *
 * The chats (sessions, messages, translations, images) are NOT in Moodle's
 * database any more: they live in the chatbot backend. So export and deletion
 * are requests to the backend (/privacy/*). If the backend cannot be reached
 * or refuses, an exception is thrown -- Moodle then shows the request as
 * failed instead of claiming that the data was erased.
 */
class provider implements
    \core_privacy\local\metadata\provider,
    \core_privacy\local\request\plugin\provider,
    core_userlist_provider {

    public static function get_metadata(collection $collection): collection {

        // Everything is sent to, and stored by, the chatbot backend.
        $collection->add_external_location_link(
            'chatbackend',
            [
                'userid'   => 'privacy:metadata:chatbackend:userid',
                'courseid' => 'privacy:metadata:chatbackend:courseid',
                'title'    => 'privacy:metadata:chatbackend:title',
                'content'  => 'privacy:metadata:chatbackend:content',
                'images'   => 'privacy:metadata:chatbackend:images',
                'times'    => 'privacy:metadata:chatbackend:times',
            ],
            'privacy:metadata:chatbackend'
        );

        $collection->add_external_location_link(
            'mistral_ai',
            [
                'content' => 'privacy:metadata:mistral:content',
            ],
            'privacy:metadata:mistral'
        );

        return $collection;
    }

    /** Does the backend hold chats of this user? */
    private static function has_data(int $userid): bool {
        $answer = (new api_client())->post_internal_strict('/privacy/user/summary', ['target_user_id' => $userid]);
        return (int) ($answer['sessions'] ?? 0) > 0;
    }

    /** Erases the user's chats in the backend (rows and image files). */
    private static function erase(int $userid): void {
        global $DB;

        $answer = (new api_client())->post_internal_strict('/privacy/user/delete', ['target_user_id' => $userid]);
        if (($answer['status'] ?? '') !== 'deleted') {
            throw new \moodle_exception('apierror', 'local_ai_system', '', null, 'unexpected answer to the delete request');
        }

        // Leftovers of the time before the chats moved to the backend (old test data), if those tables still exist.
        $manager = $DB->get_manager();
        if ($manager->table_exists('local_ai_system_sessions')) {
            $sessions = $DB->get_records('local_ai_system_sessions', ['user_id' => $userid], '', 'id, session_id');
            foreach ($sessions as $session) {
                if ($manager->table_exists('local_ai_system_messages')) {
                    $messages = $DB->get_records('local_ai_system_messages', ['session_id' => $session->session_id], '', 'id');
                    if (!empty($messages) && $manager->table_exists('local_ai_system_message_translations')) {
                        [$insql, $inparams] = $DB->get_in_or_equal(array_keys($messages));
                        $DB->delete_records_select('local_ai_system_message_translations', "message_id $insql", $inparams);
                    }
                    $DB->delete_records('local_ai_system_messages', ['session_id' => $session->session_id]);
                }
            }
            $DB->delete_records('local_ai_system_sessions', ['user_id' => $userid]);
        }
    }

    public static function get_contexts_for_userid(int $userid): contextlist {
        $contextlist = new contextlist();
        if (self::has_data($userid)) {
            $contextlist->add_user_context($userid);
        }
        return $contextlist;
    }

    public static function get_users_in_context(userlist $userlist) {
        $context = $userlist->get_context();
        if ($context->contextlevel !== CONTEXT_USER) {
            return;
        }
        if (self::has_data((int) $context->instanceid)) {
            $userlist->add_user((int) $context->instanceid);
        }
    }

    public static function export_user_data(approved_contextlist $contextlist) {
        $userid = (int) $contextlist->get_user()->id;

        foreach ($contextlist->get_contexts() as $context) {
            if ($context->contextlevel !== CONTEXT_USER || (int) $context->instanceid !== $userid) {
                continue;
            }

            $answer = (new api_client())->post_internal_strict('/privacy/user/export', ['target_user_id' => $userid]);

            foreach (($answer['sessions'] ?? []) as $session) {
                $messages = [];
                foreach ($session['messages'] as $message) {
                    $translations = [];
                    foreach ($message['translations'] as $translation) {
                        $translations[] = [
                            'language'   => $translation['language'],
                            'content'    => $translation['content'],
                            'created_at' => transform::datetime($translation['created_at']),
                        ];
                    }
                    $messages[] = [
                        'role'              => $message['role'],
                        'content'           => $message['content'],
                        'is_active_version' => $message['is_active_version'],
                        'image'             => $message['image'],
                        'tokens_used'       => $message['tokens_used'],
                        'created_at'        => transform::datetime($message['created_at']),
                        'translations'      => $translations,
                    ];
                }

                writer::with_context($context)->export_data(
                    [get_string('pluginname', 'local_ai_system'), $session['session_id']],
                    (object) [
                        'title'      => $session['title'],
                        'course_id'  => $session['course_id'],
                        'language'   => $session['language'],
                        'archived'   => $session['archived'],
                        'created_at' => transform::datetime($session['created_at']),
                        'updated_at' => transform::datetime($session['updated_at']),
                        'messages'   => $messages,
                    ]
                );
            }
        }
    }

    public static function delete_data_for_all_users_in_context(\context $context) {
        if ($context->contextlevel === CONTEXT_USER) {
            self::erase((int) $context->instanceid);
        }
    }

    public static function delete_data_for_user(approved_contextlist $contextlist) {
        $userid = (int) $contextlist->get_user()->id;

        foreach ($contextlist->get_contexts() as $context) {
            if ($context->contextlevel === CONTEXT_USER && (int) $context->instanceid === $userid) {
                self::erase($userid);
            }
        }
    }

    public static function delete_data_for_users(approved_userlist $userlist) {
        $context = $userlist->get_context();
        if ($context->contextlevel !== CONTEXT_USER) {
            return;
        }
        foreach ($userlist->get_userids() as $userid) {
            if ((int) $userid === (int) $context->instanceid) {
                self::erase((int) $userid);
            }
        }
    }
}
