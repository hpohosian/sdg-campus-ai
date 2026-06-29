<?php
defined('MOODLE_INTERNAL') || die();

$observers = [
    [
        'eventname'   => '\core\event\course_created',
        'callback'    => '\local_ai_system\observer::course_changed',
        'includefile' => '/local/ai_system/classes/observer.php',
        'priority'    => 100,
    ],
    [
        'eventname'   => '\core\event\course_updated',
        'callback'    => '\local_ai_system\observer::course_changed',
        'includefile' => '/local/ai_system/classes/observer.php',
        'priority'    => 100,
    ],
    [
        'eventname'   => '\core\event\course_module_created',
        'callback'    => '\local_ai_system\observer::course_changed',
        'includefile' => '/local/ai_system/classes/observer.php',
        'priority'    => 100,
    ],
    [
        'eventname'   => '\core\event\course_module_updated',
        'callback'    => '\local_ai_system\observer::course_changed',
        'includefile' => '/local/ai_system/classes/observer.php',
        'priority'    => 100,
    ],
    [
        'eventname'   => '\core\event\course_module_deleted',
        'callback'    => '\local_ai_system\observer::course_changed',
        'includefile' => '/local/ai_system/classes/observer.php',
        'priority'    => 100,
    ],
    [
        'eventname'   => '\core\event\course_section_updated',
        'callback'    => '\local_ai_system\observer::course_changed',
        'includefile' => '/local/ai_system/classes/observer.php',
        'priority'    => 100,
    ],
];