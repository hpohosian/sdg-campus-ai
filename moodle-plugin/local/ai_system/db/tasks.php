<?php

defined('MOODLE_INTERNAL') || die();

// Daily at 03:17 (server time). Registered when the plugin version is raised.
$tasks = [
    [
        'classname' => 'local_ai_system\task\cleanup',
        'blocking'  => 0,
        'minute'    => '17',
        'hour'      => '3',
        'day'       => '*',
        'month'     => '*',
        'dayofweek' => '*',
    ],
];
