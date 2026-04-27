define([
    'core/ajax',
    'core/str',
    'core/notification',
], function(Ajax, Str, Notification, marked) {

    const ChatBot = {
        sessionId: null,
        isLoading: false,

        init(sessionId) {
            this.sessionId = sessionId;

            if (window.marked) {
                window.marked.setOptions({
                    breaks: true,
                    gfm: true
                });
            }

            this.bindEvents();
            this.scrollToBottom();
            this.bindSessionEvents();
            this.bindNewSessionEvent();
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
                                
                this.appendMessage('assistant', response);
            } catch (err) {
                Notification.exception(err);
            } finally {
                this.setLoading(false);
            }
        },

        appendMessage(role, content) {
            const container = document.getElementById('ai-messages-container');

            const div = document.createElement('div');
            div.className = `ai-message ai-message--${role}`;

            const bubble = document.createElement('div');
            bubble.className = 'ai-message-bubble';

            const text = document.createElement('div');
            text.className = 'ai-message-content';

            const clean = (content || '').trim();

            text.innerHTML = window.marked.parse(clean);

            bubble.appendChild(text);
            div.appendChild(bubble);
            container.appendChild(div);

            this.scrollToBottom();
        },

        renderMarkdown(text) {
            // Use marked.js or a simple custom renderer
            // Escape HTML first, then render markdown syntax
            // return marked.parse(text, {sanitize: true});

            return marked.parse(text);
        },

        setLoading(state) {
            this.isLoading = state;
            document.getElementById('ai-typing-indicator').hidden = !state;
            document.getElementById('ai-send-btn').disabled = state;
        },

        scrollToBottom() {
            const container = document.getElementById('ai-messages-container');
            container.scrollTop = container.scrollHeight;
        },

        bindRenamePopup() {
            const popup = document.getElementById('ai-rename-popup');
            const input = document.getElementById('ai-rename-input');
            let currentSessionId = null;

            document.querySelectorAll('.ai-session-menu').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();

                    currentSessionId = btn.dataset.sessionId;

                    const titleEl = btn.parentElement.querySelector('.ai-session-title');
                    input.value = titleEl.textContent.trim();

                    popup.classList.remove('hidden');
                });
            });

            document.getElementById('ai-rename-cancel').addEventListener('click', () => {
                popup.classList.add('hidden');
            });

            document.getElementById('ai-rename-save').addEventListener('click', async () => {

                const newTitle = input.value.trim();

                if (!newTitle) return;

                await Ajax.call([{
                    methodname: 'local_ai_system_rename_session',
                    args: {
                        session_id: currentSessionId,
                        title: newTitle
                    }
                }]);

                location.reload();
            });

            popup.addEventListener('click', (e) => {
                if (e.target === popup) {
                    popup.classList.add('hidden');
                }
            });
        },

        bindSessionEvents() {
            document.querySelectorAll('.ai-session-item').forEach(el => {
                el.addEventListener('click', async () => {

                    const sessionId = el.dataset.sessionId;

                    const result = await Ajax.call([{
                        methodname: 'local_ai_system_get_history',
                        args: { session_id: sessionId }
                    }])[0];


                    console.log("result", result);
                    

                    // const data = JSON.parse(result.messages);
                    const data = result;

                    const container = document.getElementById('ai-messages-container');
                    container.innerHTML = '';

                    result.messages.forEach(msg => {
                        this.appendMessage(msg.role, msg.content_raw);
                    });

                    this.sessionId = sessionId;

                    document.querySelectorAll('.ai-session-item')
                        .forEach(e => e.classList.remove('active'));

                    el.classList.add('active');
                });
            });

            this.bindRenamePopup();
        },

        bindNewSessionEvent() {
            const btn = document.querySelector('.ai-chatbot-new-session');

            if (!btn) {
                return;
            }

            btn.addEventListener('click', async () => {

                const result = await Ajax.call([{
                    methodname: 'local_ai_system_create_session',
                    args: {}
                }])[0];

                this.sessionId = result.session_id;

                const container = document.getElementById('ai-messages-container');
                container.innerHTML = '';

                location.reload();
            });
        },
    };

    return {init: (sessionId) => ChatBot.init(sessionId)};
});
