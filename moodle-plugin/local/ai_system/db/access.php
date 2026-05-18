<?php

defined('MOODLE_INTERNAL') || die();

$capabilities = [

    // =========================
    // Use chatbot
    // =========================
    'local_ai_system:use_chatbot' => [

        'captype' => 'read',
        'contextlevel' => CONTEXT_SYSTEM,

        'archetypes' => [
            'user'    => CAP_ALLOW,
            'student' => CAP_ALLOW,
            'teacher' => CAP_ALLOW,
            'manager' => CAP_ALLOW,
            'editingteacher' => CAP_ALLOW
        ],
    ],

    // =========================
    // View history
    // =========================
    'local_ai_system:view_history' => [

        'captype' => 'read',
        'contextlevel' => CONTEXT_SYSTEM,

        'archetypes' => [
            'teacher' => CAP_ALLOW,
            'manager' => CAP_ALLOW,
            'editingteacher' => CAP_ALLOW
        ],
    ],
];