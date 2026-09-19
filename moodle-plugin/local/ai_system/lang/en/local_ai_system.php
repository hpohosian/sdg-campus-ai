<?php
$string['pluginname'] = 'AI System';
$string['chatpage'] = 'AI Chat';
$string['send'] = 'Send';
$string['type_message'] = 'Type your message...';
$string['new_session'] = 'New Chat';
$string['chatbot_title'] = 'SDG-Campus AI Chatbot';
$string['rename_chat_header'] = 'Rename Chat';
$string['save_chat_name'] = 'Save';
$string['cancel_chat_name'] = 'Cancel';
$string['archive'] = 'Archive';
$string['archive_chat'] = 'Archive';
$string['rename_chat'] = 'Rename';
$string['delete_chat'] = 'Delete';
$string['dearchive_chat'] = 'Unarchive';
$string['archive_empty'] = 'No archived chats';
$string['apibaseurl'] = 'AI API base URL';
$string['apibaseurl_desc'] = 'Base URL of the Python RAG/chatbot API';
$string['internalapikey'] = 'Internal API key';
$string['internalapikey_desc'] = 'Shared secret used to authenticate server-to-server requests from Moodle to the Python API';
$string['reindexfailed'] = 'Course reindexing request failed: {$a}';
$string['pluginname'] = 'AI System';
$string['select_course'] = 'Course for new chat';
$string['all_my_courses'] = 'All my courses';
$string['language_original'] = 'Original';
$string['language_picker_label'] = 'Chat language';
$string['translating'] = 'Translating...';
$string['loading_original'] = 'Loading original...';
$string['pinned'] = 'Pinned';
$string['today'] = 'Today';
$string['previous'] = 'Previous';
$string['pin_chat'] = 'Pin chat';
$string['unpin_chat'] = 'Unpin chat';
$string['coming_soon'] = 'Coming soon';
$string['switch_theme'] = 'Switch theme';
$string['no_pinned_chats'] = 'No pinned chats yet';
$string['attach_image'] = 'Attach image';
$string['this_week'] = 'This week';
$string['this_month'] = 'This month';

// Privacy API
$string['privacy:metadata:sessions'] = 'Information about your chatbot sessions';
$string['privacy:metadata:sessions:user_id'] = 'The ID of the user who owns the session';
$string['privacy:metadata:sessions:course_id'] = 'The course the session was linked to, if any';
$string['privacy:metadata:sessions:title'] = 'The title of the chat session';
$string['privacy:metadata:sessions:language'] = 'The display language selected for the session';
$string['privacy:metadata:sessions:created_at'] = 'The time the session was created';
$string['privacy:metadata:sessions:updated_at'] = 'The time the session was last updated';

$string['privacy:metadata:messages'] = 'Individual messages exchanged with the chatbot';
$string['privacy:metadata:messages:role'] = 'Whether the message was sent by the user or the assistant';
$string['privacy:metadata:messages:content'] = 'The text content of the message';
$string['privacy:metadata:messages:image_path'] = 'The path to an image attached to the message, if any';
$string['privacy:metadata:messages:tokens_used'] = 'The number of tokens used to generate the message';
$string['privacy:metadata:messages:created_at'] = 'The time the message was sent';

$string['privacy:metadata:translations'] = 'Translations of chatbot messages into other languages';
$string['privacy:metadata:translations:language'] = 'The language of the translation';
$string['privacy:metadata:translations:content'] = 'The translated text content';
$string['privacy:metadata:translations:created_at'] = 'The time the translation was created';

$string['privacy:metadata:mistral'] = 'To generate responses, chat content is sent to Mistral AI, a third-party language model provider';
$string['privacy:metadata:mistral:content'] = 'The message content sent for processing';

$string['privacy:metadata:mistral'] = 'To generate responses, chat content is sent to Mistral AI (hosted in the EU), which retains it for up to 30 days for abuse-monitoring purposes before deletion, unless zero data retention has been configured for this integration';

$string['apisecret'] = 'API secret';
$string['apisecret_desc'] = 'Shared HMAC secret used to sign requests between Moodle and the Python API';