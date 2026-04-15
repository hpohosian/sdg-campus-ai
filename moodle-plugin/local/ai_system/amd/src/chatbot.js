define(['core/ajax', 'core/str', 'core/notification'], function(Ajax, Str, Notification) {

    const ChatBot = {
        sessionId: null,
        isLoading: false,

        init(sessionId) {
            this.sessionId = sessionId;
            this.bindEvents();
            this.scrollToBottom();
        },

        bindEvents() {
            const sendBtn = document.getElementById('ai-send-btn');
            const input = document.getElementById('ai-message-input');

            sendBtn.addEventListener('click', () => this.sendMessage());
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        },

        async sendMessage() {
            if (this.isLoading) {
                return;
            }
            const input = document.getElementById('ai-message-input');
            const message = input.value.trim();
            if (!message) {
                return;
            }

            input.value = '';
            this.setLoading(true);
            this.appendMessage('user', message);

            try {
                const result = await Ajax.call([{
                    methodname: 'local_ai_system_send_message',
                    args: {
                        session_id: this.sessionId,
                        message: message,
                    }
                }])[0];

                console.log("REQUEST SENT:", message);
                console.log("RAW RESULT:", result);

                const response = result.message; 
                const newSessionId = result.session_id; 

                if (newSessionId) {
                    this.sessionId = newSessionId;
                }

                console.log("RESPONSE:", result.message);
                console.log("SESSION:", result.session_id);
                                
                this.appendMessage('assistant', response, true);
            } catch (err) {
                Notification.exception(err);
            } finally {
                this.setLoading(false);
            }
        },

        appendMessage(role, content, isMarkdown = false) {
            const container = document.getElementById('ai-messages-container');
            const div = document.createElement('div');
            div.className = `ai-message ai-message--${role}`;

            if (isMarkdown) {
                // Use marked.js (load via AMD) for markdown rendering
                div.innerHTML = this.renderMarkdown(content);
            } else {
                div.textContent = content;
            }

            container.appendChild(div);
            this.scrollToBottom();
        },

        renderMarkdown(text) {
            // Use marked.js or a simple custom renderer
            // Escape HTML first, then render markdown syntax
            // return marked.parse(text, {sanitize: true});

            return text;
        },

        setLoading(state) {
            this.isLoading = state;
            document.getElementById('ai-typing-indicator').hidden = !state;
            document.getElementById('ai-send-btn').disabled = state;
        },

        scrollToBottom() {
            const container = document.getElementById('ai-messages-container');
            container.scrollTop = container.scrollHeight;
        }
    };

    return {init: (sessionId) => ChatBot.init(sessionId)};
});
