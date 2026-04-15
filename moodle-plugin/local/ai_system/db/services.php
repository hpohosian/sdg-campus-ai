<?php
$functions = [
    'local_ai_system_send_message' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'send_message',
        'description' => 'Send a message to the AI chatbot',
        'type'        => 'write',
        'ajax'        => true,
        'loginrequired' => true,
    ],
    'local_ai_system_get_history' => [
        'classname'   => 'local_ai_system\external\chatbot_api',
        'methodname'  => 'get_history',
        'description' => 'Get chat history for a session',
        'type'        => 'read',
        'ajax'        => true,
        'loginrequired' => true,
    ],
];
