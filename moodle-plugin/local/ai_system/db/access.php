<?php

defined('MOODLE_INTERNAL') || die();

$capabilities = [

    // =========================
    // Use chatbot
    // =========================
    'local/ai_system:use_chatbot' => [

        'captype' => 'read',
        'contextlevel' => CONTEXT_SYSTEM,

        'archetypes' => [
            'student' => CAP_ALLOW,
            'teacher' => CAP_ALLOW,
            'manager' => CAP_ALLOW,
            'editingteacher' => CAP_ALLOW
        ],
    ],

    // =========================
    // View history
    // =========================
    'local/ai_system:view_history' => [

        'captype' => 'read',
        'contextlevel' => CONTEXT_SYSTEM,

        'archetypes' => [
            'teacher' => CAP_ALLOW,
            'manager' => CAP_ALLOW,
            'editingteacher' => CAP_ALLOW
        ],
    ],

];