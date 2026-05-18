define([
    'core/ajax',
    'core/notification'
], function(Ajax, Notification) {

    const ChatBot = {

        state: {
            sessionId: null,
            sessions: [],
            // messages: {},
            // activeMessages: [],
            isStreaming: false,
            controller: null,
            shouldAutoScroll: true,
        },

        init(sessionId) {
            this.state.sessionId = sessionId;

            this.initMarkdown();
            this.bindUI();
            this.bindSessions();
            this.bindNewSession();

            this.scrollToBottom();

            const container = document.getElementById('ai-messages-container');

            container.addEventListener('scroll', () => {
                const nearBottom =
                    container.scrollHeight - container.scrollTop - container.clientHeight < 50;

                this.shouldAutoScroll = nearBottom;
            });
        },

        addSessionToSidebar(sessionId, title) {
            const list = document.querySelector('.ai-chatbot-sidebar');
            if (!list) return;

            document.querySelectorAll('.ai-session-item')
                .forEach(e => e.classList.remove('active'));

            const el = document.createElement('div');
            el.className = 'ai-session-item active';
            el.dataset.sessionId = sessionId;
            el.textContent = title;

            list.prepend(el);

            el.addEventListener('click', async () => {
                const result = await Ajax.call([{
                    methodname: 'local_ai_system_get_messages',
                    args: { session_id: sessionId }
                }])[0];

                this.state.sessionId = sessionId;

                const container = document.getElementById('ai-messages-container');
                container.innerHTML = '';

                const messages = Array.isArray(result) ? result : (result.messages ?? []);

                messages.forEach(msg => {
                    this.appendMessage(msg.role, msg.content);
                });

                document.querySelectorAll('.ai-session-item')
                    .forEach(e => e.classList.remove('active'));

                el.classList.add('active');
            });
        },

        // for messages
        async ensureSession() {
            if (this.state.sessionId) {
                return this.state.sessionId;
            }

            const sessionNumber = document.querySelectorAll('.ai-session-item').length + 1;

            const result = await Ajax.call([{
                methodname: 'local_ai_system_create_session',
                args: {
                    title: `New Chat ${sessionNumber}`
                }
            }])[0];

            this.state.sessionId = result.session_id;

            this.addSessionToSidebar(result.session_id, `New Chat ${sessionNumber}`);

            return this.state.sessionId;
        },

        // for new chat button
        async createNewSession() {
            this.state.sessionId = result.session_id;

            const sessionNumber = document.querySelectorAll('.ai-session-item').length + 1;

            const result = await Ajax.call([{
                methodname: 'local_ai_system_create_session',
                args: {
                    title: `New Chat ${sessionNumber}`
                }
            }])[0];

            this.addSessionToSidebar(result.session_id, `New Chat ${sessionNumber}`);

            return this.state.sessionId;
        },

        scrollToBottom() {
            if (!this.shouldAutoScroll) return;

            const container = document.getElementById('ai-messages-container');
            container.scrollTop = container.scrollHeight;
        },

        // =========================
        // MARKDOWN
        // =========================
        initMarkdown() {
            if (window.marked) {
                window.marked.setOptions({
                    breaks: true,
                    gfm: true
                });
            }
        },


        updateUIState() {
            const input = document.getElementById('ai-message-input');
            const sendBtn = document.getElementById('ai-send-btn');
            const stopBtn = document.getElementById('ai-stop-btn');

            const isStreaming = this.state.isStreaming;

            if (input) input.disabled = isStreaming;
            if (sendBtn) sendBtn.disabled = isStreaming;

            if (stopBtn) {
                stopBtn.disabled = !isStreaming;
            }
        },

        // =========================
        // UI BINDINGS
        // =========================
        bindUI() {
            const sendBtn = document.getElementById('ai-send-btn');
            const input = document.getElementById('ai-message-input');
            const stopBtn = document.getElementById('ai-stop-btn');

            const send = () => {
                const message = input.value.trim();
                if (!message) return;

                input.value = '';
                this.sendMessageStream(message);
            };

            sendBtn.addEventListener('click', () => {
                if (this.state.isStreaming) return;
                send();
            });

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (this.state.isStreaming) return;
                    send();
                }
            });

            if (stopBtn) {
                stopBtn.addEventListener('click', () => {
                    if (this.state.controller) {
                        this.state.controller.abort();
                        this.state.isStreaming = false;
                        this.updateUIState();
                    }
                });
            }
        },

        // =========================
        // STREAM MESSAGE
        // =========================
        async sendMessageStream(message) {

            if (this.state.isStreaming) return;

            this.state.isStreaming = true;
            this.state.controller = new AbortController();
            this.updateUIState();

            this.appendMessage('user', message);

            const bubble = this.createAssistantBubble();
            let fullText = '';

            await this.ensureSession();

            try {
                const response = await fetch(
                    M.cfg.wwwroot + '/local/ai_system/ajax/stream.php',
                    {
                        method: 'POST',
                        signal: this.state.controller.signal,
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded'
                        },
                        body: new URLSearchParams({
                            session_id: this.state.sessionId,
                            message: message
                        })
                    }
                );

                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');

                let buffer = '';

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value, { stream: true });

                    buffer += chunk;

                    const lines = buffer.split('\n');

                    buffer = lines.pop();
                    
                    for (let line of lines) {
                        line = line.trim();

                        if (!line.startsWith('data:')) continue;

                        const text = line.replace(/^data:\s?/, ''); 

                        if (text === '[DONE]') continue;

                        fullText += text;

                        bubble.innerText = fullText;
                        this.scrollToBottom();
                    }
                }
            } catch (e) {
                console.error(e);
                this.state.isStreaming = false;
                this.state.controller = null;
                this.updateUIState();
            } finally {
                this.state.isStreaming = false;
                this.state.controller = null;
                this.updateUIState();
                bubble.innerHTML = window.marked.parse(fullText || '');
                this.scrollToBottom();
            }
        },

        // =========================
        // MESSAGES UI
        // =========================
        appendMessage(role, content) {

            const container = document.getElementById('ai-messages-container');

            const wrap = document.createElement('div');
            wrap.className = `ai-message ai-message--${role}`;

            const bubble = document.createElement('div');
            bubble.className = 'ai-message-bubble';

            const text = document.createElement('div');
            text.className = 'ai-message-content';

            text.innerHTML = window.marked.parse(content || '');

            bubble.appendChild(text);
            wrap.appendChild(bubble);
            container.appendChild(wrap);

            this.scrollToBottom();
        },

        createAssistantBubble() {

            const container = document.getElementById('ai-messages-container');

            const wrap = document.createElement('div');
            wrap.className = 'ai-message ai-message--assistant';

            const bubble = document.createElement('div');
            bubble.className = 'ai-message-bubble';

            const text = document.createElement('div');
            text.className = 'ai-message-content';

            bubble.appendChild(text);
            wrap.appendChild(bubble);
            container.appendChild(wrap);

            return text;
        },

        // =========================
        // SESSIONS
        // =========================
        bindSessions() {

            document.querySelectorAll('.ai-session-item').forEach(el => {

                el.addEventListener('click', async () => {

                    const sessionId = el.dataset.sessionId;

                    const result = await Ajax.call([{
                        methodname: 'local_ai_system_get_messages',
                        args: { session_id: sessionId }
                    }])[0];

                    this.state.sessionId = sessionId;

                    const container = document.getElementById('ai-messages-container');
                    container.innerHTML = '';

                    const messages = Array.isArray(result) ? result : (result.messages ?? []);

                    messages.forEach(msg => {
                        this.appendMessage(msg.role, msg.content);  // content, не content_raw
                    });

                    document.querySelectorAll('.ai-session-item')
                        .forEach(e => e.classList.remove('active'));

                    el.classList.add('active');
                });
            });
        },

        // =========================
        // NEW SESSION
        // =========================
        bindNewSession() {

            const btn = document.querySelector('.ai-chatbot-new-session');

            if (!btn) return;

            btn.addEventListener('click', async () => {
                await this.createNewSession();

                document.getElementById('ai-messages-container').innerHTML = '';
            });
        },
    };

    return {
        init: (sessionId) => ChatBot.init(sessionId)
    };
});
