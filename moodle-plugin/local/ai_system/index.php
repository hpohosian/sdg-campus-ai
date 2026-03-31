<?php
require_once(__DIR__ . '/../../config.php');
require_login();

$PAGE->set_url(new moodle_url('/local/ai_system/index.php'));
$PAGE->set_context(context_system::instance());
$PAGE->set_title(get_string('chatpage', 'local_ai_system'));
$PAGE->set_heading(get_string('chatpage', 'local_ai_system'));

echo $OUTPUT->header();
?>

<h2><?php echo get_string('chatpage', 'local_ai_system'); ?></h2>

<input type="text" id="chat-input" placeholder="<?php echo get_string('message_placeholder', 'local_ai_system'); ?>">
<button id="send-btn"><?php echo get_string('send', 'local_ai_system'); ?></button>

<div id="chat-output" style="margin-top:20px;"></div>

<script>
document.getElementById('send-btn').addEventListener('click', async () => {
    const message = document.getElementById('chat-input').value;
    if (!message) return;

    const outputDiv = document.getElementById('chat-output');
    outputDiv.innerHTML += `<p><strong>You:</strong> ${message}</p>`;

    try {
        const response = await fetch('http://localhost:8001/chat', { // <- твой FastAPI URL
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: message})
        });
        const data = await response.json();
        outputDiv.innerHTML += `<p><strong>AI:</strong> ${data.response}</p>`;
    } catch (err) {
        outputDiv.innerHTML += `<p style="color:red;">Error: ${err.message}</p>`;
    }

    document.getElementById('chat-input').value = '';
});
</script>

<?php
echo $OUTPUT->footer();