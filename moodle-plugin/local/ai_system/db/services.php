<?php
$functions = [
    'local_ai_system_get_sessions' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'get_sessions',
        'description' => 'Get all user sessions',
        'type'        => 'read',
        'ajax'        => true,
        'loginrequired' => true,
    ],

    'local_ai_system_create_session' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'create_session',
        'description' => 'Create new chat session',
        'type'        => 'write',
        'ajax'        => true,
        'loginrequired' => true,
    ],

    'local_ai_system_get_session' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'get_session',
        'description' => 'Get single session info',
        'type'        => 'read',
        'ajax'        => true,
        'loginrequired' => true,
    ],

    'local_ai_system_update_session' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'update_session',
        'description' => 'Update session (rename etc)',
        'type'        => 'write',
        'ajax'        => true,
        'loginrequired' => true,
    ],

    'local_ai_system_delete_session' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'delete_session',
        'description' => 'Delete session',
        'type'        => 'write',
        'ajax'        => true,
        'loginrequired' => true,
    ],

    'local_ai_system_archive_session' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'archive_session',
        'description' => 'Archive session',
        'type'        => 'write',
        'ajax'        => true,
        'loginrequired' => true,
    ],

    'local_ai_system_dearchive_session' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'dearchive_session',
        'description' => 'Restore archived session',
        'type'        => 'write',
        'ajax'        => true,
        'loginrequired' => true,
    ],


    'local_ai_system_get_messages' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'get_messages',
        'description' => 'Get messages for session',
        'type'        => 'read',
        'ajax'        => true,
        'loginrequired' => true,
    ],

    'local_ai_system_translate_message' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'translate_message',
        'description' => 'Translate one message into the session language (progressive chat translation)',
        'type'        => 'read',
        'ajax'        => true,
        'loginrequired' => true,
        // Several translations run in parallel; without this Moodle's session
        // lock would make them wait for each other one by one.
        'readonlysession' => true,
    ],

    'local_ai_system_save_partial_message' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'save_partial_message',
        'description' => 'Persist partially generated assistant response after Stop',
        'type'        => 'write',
        'ajax'        => true,
        'loginrequired' => true,
    ],

    'local_ai_system_create_quiz' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'create_quiz',
        'description' => 'Generate a self-study quiz from the course materials and add it to the chat',
        'type'        => 'write',
        'ajax'        => true,
        'loginrequired' => true,
        // Generating takes 10-30 s; the user's other requests (sidebar,
        // other chats) must not wait for it behind Moodle's session lock.
        'readonlysession' => true,
    ],

    'local_ai_system_answer_quiz' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'answer_quiz',
        'description' => 'Answer one quiz question (checked by the backend)',
        'type'        => 'write',
        'ajax'        => true,
        'loginrequired' => true,
        'readonlysession' => true,
    ],
];
