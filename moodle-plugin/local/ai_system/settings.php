<?php
defined('MOODLE_INTERNAL') || die();

if ($hassiteconfig) {
    $settings = new admin_settingpage('local_ai_system', get_string('pluginname', 'local_ai_system'));

    $settings->add(new admin_setting_configtext(
        'local_ai_system/api_base_url',
        get_string('apibaseurl', 'local_ai_system'),
        get_string('apibaseurl_desc', 'local_ai_system'),
        'http://127.0.0.1:8001',
        PARAM_URL
    ));

    $settings->add(new admin_setting_configpasswordunmask(
        'local_ai_system/internal_api_key',
        get_string('internalapikey', 'local_ai_system'),
        get_string('internalapikey_desc', 'local_ai_system'),
        ''
    ));

    $settings->add(new admin_setting_configpasswordunmask(
        'local_ai_system/api_secret',
        get_string('apisecret', 'local_ai_system'),
        get_string('apisecret_desc', 'local_ai_system'),
        ''
    ));

    $ADMIN->add('localplugins', $settings);
}