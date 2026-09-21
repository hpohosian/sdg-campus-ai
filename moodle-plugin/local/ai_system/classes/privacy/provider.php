<?php

namespace local_ai_system\privacy;

use core_privacy\local\metadata\collection;
use core_privacy\local\request\approved_contextlist;
use core_privacy\local\request\contextlist;
use core_privacy\local\request\writer;
use core_privacy\local\request\userlist;
use context_user;

defined('MOODLE_INTERNAL') || die();

class provider implements
    \core_privacy\local\metadata\provider,
    \core_privacy\local\request\plugin\provider {

    /**
     * Describe what personal data this plugin stores.
     */
    public static function get_metadata(collection $collection): collection {

        $collection->add_database_table(
            'local_ai_system_sessions',
            [
                'user_id'    => 'privacy:metadata:sessions:user_id',
                'course_id'  => 'privacy:metadata:sessions:course_id',
                'title'      => 'privacy:metadata:sessions:title',
                'language'   => 'privacy:metadata:sessions:language',
                'created_at' => 'privacy:metadata:sessions:created_at',
                'updated_at' => 'privacy:metadata:sessions:updated_at',
            ],
            'privacy:metadata:sessions'
        );

        $collection->add_database_table(
            'local_ai_system_messages',
            [
                'role'         => 'privacy:metadata:messages:role',
                'content'      => 'privacy:metadata:messages:content',
                'image_path'   => 'privacy:metadata:messages:image_path',
                'tokens_used'  => 'privacy:metadata:messages:tokens_used',
                'created_at'   => 'privacy:metadata:messages:created_at',
            ],
            'privacy:metadata:messages'
        );

        $collection->add_database_table(
            'local_ai_system_message_translations',
            [
                'language'   => 'privacy:metadata:translations:language',
                'content'    => 'privacy:metadata:translations:content',
                'created_at' => 'privacy:metadata:translations:created_at',
            ],
            'privacy:metadata:translations'
        );

        // The plugin also sends chat content to a third-party LLM provider
        // (Mistral) for generating responses.
        $collection->add_external_location_link(
            'mistral_ai',
            [
                'content' => 'privacy:metadata:mistral:content',
            ],
            'privacy:metadata:mistral'
        );

        return $collection;
    }

    /**
     * Every user who has ever used the chatbot has personal data
     * in their own user context (data isn't course-scoped for
     * privacy purposes, even though sessions may reference a course).
     */
    public static function get_contexts_for_userid(int $userid): contextlist {
        $contextlist = new contextlist();

        $sql = "SELECT COUNT(*)
                  FROM {local_ai_system_sessions}
                 WHERE user_id = :userid";

        if ($DB = self::db()) {
            $exists = $DB->record_exists_sql($sql, ['userid' => $userid]);
            if ($exists) {
                $context = context_user::instance($userid, IGNORE_MISSING);
                if ($context) {
                    $contextlist->add_user_context($userid);
                }
            }
        }

        return $contextlist;
    }

    /**
     * Export all sessions/messages/translations belonging to the user.
     */
    public static function export_user_data(approved_contextlist $contextlist): void {
        global $DB;

        $userid = $contextlist->get_user()->id;

        $sessions = $DB->get_records('local_ai_system_sessions', ['user_id' => $userid]);

        foreach ($sessions as $session) {
            $context = context_user::instance($userid);

            $messages = $DB->get_records('local_ai_system_messages', ['session_id' => $session->session_id]);

            $exportedmessages = [];
            foreach ($messages as $message) {

                $translations = $DB->get_records('local_ai_system_message_translations', ['message_id' => $message->id]);
                $exportedtranslations = [];
                foreach ($translations as $translation) {
                    $exportedtranslations[] = [
                        'language'   => $translation->language,
                        'content'    => $translation->content,
                        'created_at' => \core_privacy\local\request\transform::datetime($translation->created_at),
                    ];
                }

                $exportedmessages[] = [
                    'role'         => $message->role,
                    'content'      => $message->content,
                    'image_path'   => $message->image_path,
                    'tokens_used'  => $message->tokens_used,
                    'created_at'   => \core_privacy\local\request\transform::datetime($message->created_at),
                    'translations' => $exportedtranslations,
                ];
            }

            $data = (object) [
                'title'      => $session->title,
                'course_id'  => $session->course_id,
                'language'   => $session->language,
                'created_at' => \core_privacy\local\request\transform::datetime($session->created_at),
                'updated_at' => \core_privacy\local\request\transform::datetime($session->updated_at),
                'messages'   => $exportedmessages,
            ];

            writer::with_context($context)->export_data(
                [get_string('pluginname', 'local_ai_system'), $session->session_id],
                $data
            );
        }
    }

    /**
     * Delete all data for a user across all approved contexts.
     */
    public static function delete_data_for_user(approved_contextlist $contextlist): void {
        global $DB;

        $userid = $contextlist->get_user()->id;

        $sessions = $DB->get_records('local_ai_system_sessions', ['user_id' => $userid], '', 'id, session_id');

        foreach ($sessions as $session) {
            $messages = $DB->get_records('local_ai_system_messages', ['session_id' => $session->session_id], '', 'id');
            $messageids = array_keys($messages);

            if (!empty($messageids)) {
                [$insql, $inparams] = $DB->get_in_or_equal($messageids);
                $DB->delete_records_select('local_ai_system_message_translations', "message_id $insql", $inparams);
            }

            $DB->delete_records('local_ai_system_messages', ['session_id' => $session->session_id]);
        }

        $DB->delete_records('local_ai_system_sessions', ['user_id' => $userid]);
    }


    /**
     * Delete all user data for all users within a given context.
     *
     * All personal data in this plugin lives at the CONTEXT_USER level
     * (one context = one user), so this is never called with a course/
     * module/system context containing multiple users' data -- if it's
     * called at all, the context is a single user's, and deleting "all
     * users in it" means deleting that one user's data.
     */
    public static function delete_data_for_all_users_in_context(\context $context): void {
        if ($context->contextlevel !== CONTEXT_USER) {
            return;
        }

        global $DB;

        $userid = $context->instanceid;

        $sessions = $DB->get_records('local_ai_system_sessions', ['user_id' => $userid], '', 'id, session_id');

        foreach ($sessions as $session) {
            $messages = $DB->get_records('local_ai_system_messages', ['session_id' => $session->session_id], '', 'id');
            $messageids = array_keys($messages);

            if (!empty($messageids)) {
                [$insql, $inparams] = $DB->get_in_or_equal($messageids);
                $DB->delete_records_select('local_ai_system_message_translations', "message_id $insql", $inparams);
            }

            $DB->delete_records('local_ai_system_messages', ['session_id' => $session->session_id]);
        }

        $DB->delete_records('local_ai_system_sessions', ['user_id' => $userid]);
    }

    private static function db() {
        global $DB;
        return $DB;
    }
}