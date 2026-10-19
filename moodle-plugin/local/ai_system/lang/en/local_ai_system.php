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

// Privacy API: the chats are stored by the chatbot backend (see classes/privacy/provider.php)
$string['privacy:metadata:chatbackend'] = 'Your chats with the AI chatbot are stored by the chatbot backend service that belongs to this Moodle site (not in the Moodle database). Chats older than the configured retention period are deleted automatically.';
$string['privacy:metadata:chatbackend:userid'] = 'Your Moodle user ID, to assign the chats to you.';
$string['privacy:metadata:chatbackend:courseid'] = 'The course a chat was linked to, if any.';
$string['privacy:metadata:chatbackend:title'] = 'The title of the chat.';
$string['privacy:metadata:chatbackend:content'] = 'The messages you wrote, the answers of the chatbot and their translations.';
$string['privacy:metadata:chatbackend:images'] = 'Images you attached to messages.';
$string['privacy:metadata:chatbackend:times'] = 'When the chat was created and last used, and when each message was sent.';

$string['privacy:metadata:mistral:content'] = 'The message content sent for processing';
$string['privacy:metadata:mistral'] = 'To generate responses, chat content is sent to Mistral AI (hosted in the EU), which retains it for up to 30 days for abuse-monitoring purposes before deletion, unless zero data retention has been configured for this integration';

$string['cleanup_task'] = 'Delete expired AI chatbot chats (retention)';
$string['apierror'] = 'The AI chatbot service did not answer correctly. Please try again later or contact the administrator.';

$string['apisecret'] = 'API secret';
$string['apisecret_desc'] = 'Shared HMAC secret used to sign requests between Moodle and the Python API';

$string['ai_system:use_chatbot'] = 'Use the AI chatbot';
$string['ai_system:view_history'] = 'View chat history';

// Redesign: sidebar search, start screen
$string['search_chats'] = 'Search chats';
$string['no_results'] = 'No chats found';
$string['empty_title'] = 'What are you working on today?';
$string['empty_subtitle'] = 'Ask about your course materials. Every answer shows where it comes from.';
$string['suggest_1'] = 'Summarize the key points of this course';
$string['suggest_2'] = 'Explain a topic in simple terms';
$string['suggest_3'] = 'Quiz me on the course content';
$string['suggest_4'] = 'Where in the materials is this covered?';
