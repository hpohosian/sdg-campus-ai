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
];
