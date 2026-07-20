define([
    'core/ajax',
    'core/notification'
], function(Ajax, Notification) {

    const ChatBot = {

        state: {
            sessionId: null,
            courseId: 0,
            isStreaming: false,
            isTranslating: false,
            controller: null,
            shouldAutoScroll: true,
            partialText: '',
            pinned: {}
        },

        init(sessionId, courseId) {
            this.state.sessionId = sessionId;
            this.state.courseId = courseId || 0;

            // Reparent floating elements to <body> so they can never be
            // clipped or mis-positioned by any ancestor's overflow/transform
            // (this is what caused the "menu hidden behind message" and
            // "popup stretches full width" bugs).
            const menu = document.getElementById('ai-context-menu');
            const popup = document.getElementById('ai-rename-popup');
            if (menu && menu.parentElement !== document.body) document.body.appendChild(menu);
            if (popup && popup.parentElement !== document.body) document.body.appendChild(popup);

            this.initMarkdown();
            this.initTheme();
            this.bindThemeToggle();
            this.bindUI();
            this.bindGlobalDelegation();
            this.bindContextMenuActions();
            this.bindRenamePopup();
            this.groupSessionsByDate();
            this.bindNewSession();
            this.bindLanguagePicker();
            this.bindHeaderPin();
            this.bindArchiveToggle();
            this.bindCoursePicker();
            this.formatServerMessageTimes();
            this.scrollToBottom();

            const activeItem = document.querySelector(`.ai-session-item[data-session-id="${sessionId}"]`);
            this.setActiveLanguage(activeItem?.dataset.language || '');

            const initialCount = document.getElementById('ai-messages-container').children.length;
            this.setCourseLock(initialCount > 0);

            const container = document.getElementById('ai-messages-container');

            container.addEventListener('scroll', () => {
                const nearBottom =
                    container.scrollHeight - container.scrollTop - container.clientHeight < 50;
                this.shouldAutoScroll = nearBottom;
            });

            container.addEventListener('click', (e) => {
                const link = e.target.closest('a');
                if (!link || !container.contains(link)) return;
                e.preventDefault();
                window.open(link.href, '_blank', 'noopener,noreferrer');
            });
        },

        // =========================
        // THEME
        // =========================
        initTheme() {
            let saved = null;
            try { saved = localStorage.getItem('ai_system_theme'); } catch (e) { /* ignore */ }

            if (saved === 'dark') {
                document.body.dataset.theme = 'dark';           // CHANGED: было document.getElementById('ai-chatbot-layout')
                const icon = document.getElementById('ai-theme-icon');
                if (icon) icon.className = 'fa fa-moon-o';
            }
        },

        bindThemeToggle() {
            const btn = document.getElementById('ai-theme-toggle');
            const icon = document.getElementById('ai-theme-icon');
            if (!btn) return;

            btn.addEventListener('click', () => {
                const isDark = document.body.dataset.theme === 'dark';   // CHANGED

                if (isDark) {
                    delete document.body.dataset.theme;                  // CHANGED
                    if (icon) icon.className = 'fa fa-sun-o';
                } else {
                    document.body.dataset.theme = 'dark';                // CHANGED
                    if (icon) icon.className = 'fa fa-moon-o';
                }

                try { localStorage.setItem('ai_system_theme', isDark ? 'light' : 'dark'); } catch (e) { /* ignore */ }
            });
        },

        // =========================
        // DATE GROUPING (front-only reorganization of server-rendered items)
        // =========================
        groupSessionsByDate() {
            const todayContainer = document.getElementById('ai-sb-today');
            const previousContainer = document.getElementById('ai-sb-previous');
            const previousGroup = document.getElementById('ai-sb-previous-group');
            if (!todayContainer || !previousContainer) return;

            const midnight = new Date();
            midnight.setHours(0, 0, 0, 0);
            const cutoff = Math.floor(midnight.getTime() / 1000);
            let movedAny = false;

            Array.from(todayContainer.children).forEach(el => {
                const ts = parseInt(el.dataset.createdAt, 10);
                if (ts && ts < cutoff) {
                    previousContainer.appendChild(el);
                    movedAny = true;
                }
            });

            if (movedAny && previousGroup) previousGroup.style.display = '';
        },

        // =========================
        // MESSAGE TIMESTAMPS + ACTIONS
        // =========================
        formatServerMessageTimes() {
            document.querySelectorAll('.ai-message-time[data-created-at]').forEach(el => {
                const ts = parseInt(el.dataset.createdAt, 10);
                if (!ts) return;
                el.textContent = this.formatTime(new Date(ts * 1000));
            });
            this.bindMessageActions(document);
        },

        bindMessageActions(scope) {
            scope.querySelectorAll('.ai-msg-action-copy').forEach(btn => {
                if (btn.dataset.bound) return;
                btn.dataset.bound = '1';
                btn.addEventListener('click', () => {
                    const bubble = btn.closest('.ai-bubble-wrap')?.querySelector('.ai-message-content');
                    if (!bubble) return;
                    navigator.clipboard.writeText(bubble.innerText).then(() => {
                        const icon = btn.querySelector('i');
                        icon.className = 'fa fa-check';
                        setTimeout(() => { icon.className = 'fa fa-clone'; }, 1000);
                    });
                });
            });

            scope.querySelectorAll('.ai-msg-action-regen, .ai-msg-action-edit').forEach(btn => {
                if (btn.dataset.bound) return;
                btn.dataset.bound = '1';
                btn.addEventListener('click', () => {
                    console.log('[ChatBot] action not implemented yet:', btn.className);
                });
            });

            scope.querySelectorAll('.ai-msg-action-up, .ai-msg-action-down').forEach(btn => {
                if (btn.dataset.bound) return;
                btn.dataset.bound = '1';
                btn.addEventListener('click', () => {
                    const row = btn.closest('.ai-message-actions');
                    row.querySelectorAll('.ai-msg-action-up, .ai-msg-action-down').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                });
            });
        },

        // =========================
        // PIN (front-only, in-memory)
        // =========================
        bindHeaderPin() {
            const btn = document.getElementById('ai-pin-header-btn');
            if (!btn) return;
            btn.addEventListener('click', () => {
                if (!this.state.sessionId) return;
                this.togglePin(this.state.sessionId);
            });
        },

        togglePin(sessionId) {
            const item = document.querySelector(`.ai-session-item[data-session-id="${sessionId}"]`);
            if (!item) return;

            const isPinned = !!this.state.pinned[sessionId];
            this.state.pinned[sessionId] = !isPinned;

            const pinIcon = item.querySelector('.ai-session-pin-icon');
            if (pinIcon) pinIcon.classList.toggle('hidden', isPinned);

            const pinnedContainer = document.getElementById('ai-sb-pinned');

            if (!isPinned) {
                this.removePinnedEmptyState();
                pinnedContainer.prepend(item);
            } else {
                const dest = item.classList.contains('ai-session-archived')
                    ? document.getElementById('ai-archive-dropdown')
                    : document.getElementById('ai-sb-today');
                dest.prepend(item);
                this.maybeShowPinnedEmptyState();
            }
        },

        removePinnedEmptyState() {
            document.getElementById('ai-pinned-empty')?.remove();
        },

        maybeShowPinnedEmptyState() {
            const pinnedContainer = document.getElementById('ai-sb-pinned');
            if (pinnedContainer && !pinnedContainer.children.length) {
                const p = document.createElement('p');
                p.className = 'ai-sb-empty';
                p.id = 'ai-pinned-empty';
                p.textContent = 'No pinned chats yet';
                pinnedContainer.appendChild(p);
            }
        },

        // =========================
        // COURSE PICKER + LOCK
        // =========================
        bindCoursePicker() {
            const toggle = document.getElementById('ai-course-toggle');
            const dropdown = document.getElementById('ai-course-dropdown');
            const currentLabel = document.getElementById('ai-course-current-label');
            if (!toggle || !dropdown) return;

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                if (toggle.classList.contains('disabled')) return;
                toggle.classList.toggle('open');
                dropdown.classList.toggle('hidden');
            });

            document.addEventListener('click', () => {
                dropdown.classList.add('hidden');
                toggle.classList.remove('open');
            });

            const options = dropdown.querySelectorAll('.ai-course-option');
            options.forEach(option => {
                if (option.dataset.courseId === '0') option.classList.add('selected');

                option.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const courseId = parseInt(option.dataset.courseId, 10) || 0;
                    this.state.courseId = courseId;

                    options.forEach(o => o.classList.remove('selected'));
                    option.classList.add('selected');

                    if (currentLabel) {
                        currentLabel.textContent = option.querySelector('.ai-course-option-label').textContent.trim();
                    }

                    dropdown.classList.add('hidden');
                    toggle.classList.remove('open');
                });
            });
        },

        // Locked only once the active chat actually has at least one
        // message (not just because a session row exists) — an empty
        // freshly-created chat still allows switching the course.
        setCourseLock(locked) {
            const toggle = document.getElementById('ai-course-toggle');
            if (!toggle) return;
            toggle.classList.toggle('disabled', !!locked);
        },

        // =========================
        // LANGUAGE PICKER
        // =========================
        bindLanguagePicker() {
            const toggle = document.getElementById('ai-language-toggle');
            const dropdown = document.getElementById('ai-language-dropdown');
            if (!toggle || !dropdown) return;

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                toggle.classList.toggle('open');
                dropdown.classList.toggle('hidden');
            });

            document.addEventListener('click', () => {
                dropdown.classList.add('hidden');
                toggle.classList.remove('open');
            });

            const options = dropdown.querySelectorAll('.ai-language-option');
            options.forEach(option => {
                option.addEventListener('click', async (e) => {
                    e.stopPropagation();

                    if (!this.state.sessionId || this.state.isTranslating) {
                        dropdown.classList.add('hidden');
                        toggle.classList.remove('open');
                        return;
                    }

                    const language = option.dataset.language || '';
                    const isReset = language === '';

                    dropdown.classList.add('hidden');
                    toggle.classList.remove('open');

                    this.state.isTranslating = true;
                    this.showTranslatingOverlay(isReset);

                    try {
                        await Ajax.call([{
                            methodname: 'local_ai_system_update_session',
                            args: { session_id: this.state.sessionId, language }
                        }])[0];

                        this.setActiveLanguage(language);

                        const result = await Ajax.call([{
                            methodname: 'local_ai_system_get_messages',
                            args: { session_id: this.state.sessionId }
                        }])[0];

                        const container = document.getElementById('ai-messages-container');
                        container.innerHTML = '';

                        const messages = Array.isArray(result) ? result : (result.messages ?? []);
                        messages.forEach(msg => this.appendMessage(msg.role, msg.content, msg.created_at));

                        const item = document.querySelector(`.ai-session-item[data-session-id="${this.state.sessionId}"]`);
                        if (item) {
                            item.dataset.language = language;
                            const badge = item.querySelector('.ai-session-lang-badge');
                            if (badge) {
                                badge.dataset.language = language;
                                badge.textContent = language;
                            }
                        }
                    } finally {
                        this.state.isTranslating = false;
                        this.hideTranslatingOverlay();
                    }
                });
            });
        },

        setActiveLanguage(language) {
            const dropdown = document.getElementById('ai-language-dropdown');
            const currentLabel = document.getElementById('ai-language-current-label');
            if (!dropdown || !currentLabel) return;

            dropdown.querySelectorAll('.ai-language-option').forEach(o => o.classList.remove('selected'));
            const target = dropdown.querySelector(`.ai-language-option[data-language="${language || ''}"]`);
            if (target) {
                target.classList.add('selected');
                currentLabel.textContent = target.querySelector('.ai-language-option-label').textContent.trim();
            }
        },

        showTranslatingOverlay(isReset) {
            const overlay = document.getElementById('ai-translating-overlay');
            const label = document.getElementById('ai-translating-label');
            if (!overlay || !label) return;
            label.textContent = isReset ? overlay.dataset.labelLoading : overlay.dataset.labelTranslating;
            overlay.classList.remove('hidden');
        },

        hideTranslatingOverlay() {
            document.getElementById('ai-translating-overlay')?.classList.add('hidden');
        },

        // =========================
        // CONTEXT MENU (single instance, mounted on <body>)
        // =========================
        openContextMenu(sessionId, btn, opts) {
            const menu = document.getElementById('ai-context-menu');
            if (!menu) return;

            menu.dataset.sessionId = sessionId;
            menu.dataset.archived = opts.archived ? '1' : '0';
            menu.querySelector('.ai-ctx-pin-label').textContent = opts.pinned ? 'Unpin' : 'Pin chat';
            menu.querySelector('.ai-ctx-archive-label').textContent = opts.archived ? 'Unarchive' : 'Archive';
            menu.querySelector('.ai-ctx-archive-icon').className = 'fa ' + (opts.archived ? 'fa-inbox' : 'fa-archive') + ' ai-ctx-archive-icon';
            
            menu.classList.remove('hidden');
            menu.style.visibility = 'hidden';
            const menuHeight = menu.offsetHeight;
            const menuWidth = menu.offsetWidth;
            menu.style.visibility = '';

            const rect = btn.getBoundingClientRect();
            const top = (window.innerHeight - rect.bottom < menuHeight && rect.top > menuHeight)
                ? rect.top - menuHeight - 4
                : rect.bottom + 4;
            let left = Math.min(rect.left, window.innerWidth - menuWidth - 8);
            left = Math.max(8, left);

            menu.style.top = top + 'px';
            menu.style.left = left + 'px';
        },

        closeContextMenu() {
            document.getElementById('ai-context-menu')?.classList.add('hidden');
        },

        bindContextMenuActions() {
            const menu = document.getElementById('ai-context-menu');
            if (!menu) return;

            menu.querySelector('.ai-ctx-pin').addEventListener('click', (e) => {
                e.stopPropagation();
                const sessionId = menu.dataset.sessionId;
                this.closeContextMenu();
                this.togglePin(sessionId);
            });

            menu.querySelector('.ai-ctx-rename').addEventListener('click', (e) => {
                e.stopPropagation();
                const sessionId = menu.dataset.sessionId;
                this.closeContextMenu();

                const item = document.querySelector(`.ai-session-item[data-session-id="${sessionId}"]`);
                const currentTitle = item?.querySelector('.ai-session-title')?.textContent.trim() ?? '';

                const popup = document.getElementById('ai-rename-popup');
                popup.classList.remove('hidden');
                popup.dataset.sessionId = sessionId;
                const input = document.getElementById('ai-rename-input');
                input.value = currentTitle;
                input.focus();
                input.select();
            });

            menu.querySelector('.ai-ctx-archive').addEventListener('click', async (e) => {
                e.stopPropagation();
                const sessionId = menu.dataset.sessionId;
                const archived = menu.dataset.archived === '1';
                this.closeContextMenu();

                const item = document.querySelector(`.ai-session-item[data-session-id="${sessionId}"]`);
                const title = item?.querySelector('.ai-session-title')?.textContent.trim() ?? 'Chat';
                const language = item?.dataset.language || '';
                const wasPinned = !!this.state.pinned[sessionId];

                await Ajax.call([{
                    methodname: archived ? 'local_ai_system_dearchive_session' : 'local_ai_system_archive_session',
                    args: { session_id: sessionId }
                }])[0];

                if (item) item.remove();

                if (archived) {
                    this.addSessionToSidebar(sessionId, title, language, wasPinned);
                    const input = document.getElementById('ai-message-input');
                    const sendBtn = document.getElementById('ai-send-btn');
                    if (input) { input.disabled = false; input.placeholder = 'Type your message...'; }
                    if (sendBtn) sendBtn.disabled = false;
                } else {
                    this.addSessionToArchive(sessionId, title, language, wasPinned);
                    if (this.state.sessionId === sessionId) {
                        this.state.sessionId = null;
                        document.getElementById('ai-messages-container').innerHTML = '';
                        document.getElementById('ai-chat-title').textContent = 'SDG-Campus AI Chatbot';
                        this.setCourseLock(false);
                    }
                }
            });

            menu.querySelector('.ai-ctx-delete').addEventListener('click', async (e) => {
                e.stopPropagation();
                const sessionId = menu.dataset.sessionId;
                this.closeContextMenu();

                if (!confirm('Delete this chat?')) return;

                await Ajax.call([{
                    methodname: 'local_ai_system_delete_session',
                    args: { session_id: sessionId }
                }])[0];

                const item = document.querySelector(`.ai-session-item[data-session-id="${sessionId}"]`);
                if (item) item.remove();

                if (this.state.sessionId === sessionId) {
                    this.state.sessionId = null;
                    document.getElementById('ai-messages-container').innerHTML = '';
                    document.getElementById('ai-chat-title').textContent = 'SDG-Campus AI Chatbot';
                    this.setCourseLock(false);
                }
            });
        },

        bindRenamePopup() {
            document.getElementById('ai-rename-save')?.addEventListener('click', async () => {
                const popup = document.getElementById('ai-rename-popup');
                const sessionId = popup.dataset.sessionId;
                const title = document.getElementById('ai-rename-input').value.trim();
                if (!title) return;

                await Ajax.call([{
                    methodname: 'local_ai_system_update_session',
                    args: { session_id: sessionId, title }
                }])[0];

                const el = document.querySelector(`.ai-session-item[data-session-id="${sessionId}"] .ai-session-title`);
                if (el) el.textContent = title;

                if (this.state.sessionId === sessionId) {
                    document.getElementById('ai-chat-title').textContent = title;
                }

                popup.classList.add('hidden');
            });

            document.getElementById('ai-rename-cancel')?.addEventListener('click', () => {
                document.getElementById('ai-rename-popup').classList.add('hidden');
            });
        },

        // =========================
        // ARCHIVE TOGGLE
        // =========================
        bindArchiveToggle() {
            const toggle = document.getElementById('ai-archive-toggle');
            const dropdown = document.getElementById('ai-archive-dropdown');
            if (!toggle || !dropdown) return;

            toggle.addEventListener('click', () => {
                toggle.classList.toggle('open');
                dropdown.classList.toggle('hidden');
            });
        },

        // =========================
        // GLOBAL CLICK DELEGATION
        // (covers both server-rendered and dynamically created session items —
        // no per-item re-binding needed anywhere anymore)
        // =========================
        bindGlobalDelegation() {
            document.addEventListener('click', (e) => {
                const menuBtn = e.target.closest('.ai-session-menu-btn');
                if (menuBtn) {
                    e.stopPropagation();
                    const item = menuBtn.closest('.ai-session-item');
                    const sessionId = item.dataset.sessionId;
                    const archived = item.classList.contains('ai-session-archived');
                    const pinned = !!this.state.pinned[sessionId];
                    this.openContextMenu(sessionId, menuBtn, { archived, pinned });
                    return;
                }

                const item = e.target.closest('.ai-session-item');
                const layout = document.getElementById('ai-chatbot-layout');
                if (item && layout && layout.contains(item)) {
                    this.closeContextMenu();          // NEW: закрываем меню перед загрузкой другого чата
                    this.loadSession(item.dataset.sessionId);
                    return;
                }

                if (!e.target.closest('#ai-context-menu')) {
                    this.closeContextMenu();
                }
            });
        },

        // =========================
        // LOAD A SESSION (regular or archived) — single source of truth
        // =========================
        async loadSession(sessionId) {
            const item = document.querySelector(`.ai-session-item[data-session-id="${sessionId}"]`);
            const title = item ? item.querySelector('.ai-session-title').textContent.trim() : 'Chat';
            const archived = item ? item.classList.contains('ai-session-archived') : false;

            this.setActiveLanguage(item?.dataset.language || '');

            const result = await Ajax.call([{
                methodname: 'local_ai_system_get_messages',
                args: { session_id: sessionId }
            }])[0];

            const messages = Array.isArray(result) ? result : (result.messages ?? []);

            const container = document.getElementById('ai-messages-container');
            container.innerHTML = '';
            messages.forEach(msg => this.appendMessage(msg.role, msg.content, msg.created_at));

            const chatTitle = document.getElementById('ai-chat-title');
            if (chatTitle) chatTitle.textContent = archived ? `${title} (archived)` : title;

            const input = document.getElementById('ai-message-input');
            const sendBtn = document.getElementById('ai-send-btn');

            if (archived) {
                if (input) { input.disabled = true; input.placeholder = 'Unarchive to send messages'; }
                if (sendBtn) sendBtn.disabled = true;
                this.state.sessionId = null;
            } else {
                if (input) { input.disabled = false; input.placeholder = 'Type your message...'; }
                if (sendBtn) sendBtn.disabled = false;
                this.state.sessionId = sessionId;
            }

            this.setCourseLock(archived || messages.length > 0);

            document.querySelectorAll('.ai-session-item').forEach(e => e.classList.remove('active'));
            if (item) item.classList.add('active');
        },

        formatTime(date) {
            const h = date.getHours();
            const m = date.getMinutes().toString().padStart(2, '0');
            return `${h}:${m}`;
        },

        renderSessionItem(sessionId, title, language, pinned) {
            const el = document.createElement('div');
            el.className = 'ai-session-item active';
            el.dataset.sessionId = sessionId;
            el.dataset.language = language || '';
            el.innerHTML = `
                <span class="ai-session-lang-badge" data-language="${language || ''}">${language || ''}</span>
                <span class="ai-session-title">${title}</span>
                <i class="fa fa-star ai-session-pin-icon${pinned ? '' : ' hidden'}" aria-hidden="true"></i>
                <button class="ai-session-menu-btn" data-session-id="${sessionId}" aria-label="Chat options">
                    <i class="fa fa-ellipsis-v"></i>
                </button>
            `;
            return el;
        },

        addSessionToSidebar(sessionId, title, language = '', pinned = false) {
            document.querySelectorAll('.ai-session-item').forEach(e => e.classList.remove('active'));
            const el = this.renderSessionItem(sessionId, title, language, pinned);

            if (pinned) {
                this.removePinnedEmptyState();
                document.getElementById('ai-sb-pinned').prepend(el);
            } else {
                document.getElementById('ai-sb-today').prepend(el);
            }
        },

        addSessionToArchive(sessionId, title, language = '', pinned = false) {
            const dropdown = document.getElementById('ai-archive-dropdown');
            if (!dropdown) return;

            const empty = dropdown.querySelector('.ai-archive-empty');
            if (empty) empty.remove();

            const el = this.renderSessionItem(sessionId, title, language, pinned);
            el.className = 'ai-session-item ai-session-archived';
            dropdown.prepend(el);
        },

        async ensureSession() {
            if (this.state.sessionId) return this.state.sessionId;

            try {
                const result = await Ajax.call([{
                    methodname: 'local_ai_system_create_session',
                    args: { course_id: this.state.courseId }
                }])[0];

                this.state.sessionId = result.session_id;
                this.addSessionToSidebar(result.session_id, result.title || 'New chat', '', false);

                return this.state.sessionId;
            } catch (e) {
                console.error('ensureSession failed:', e);
                return null;
            }
        },

        async createNewSession() {
            const sessionNumber = document.querySelectorAll('.ai-session-item').length + 1;
            const title = `New chat ${sessionNumber}`;

            const result = await Ajax.call([{
                methodname: 'local_ai_system_create_session',
                args: { title, course_id: this.state.courseId }
            }])[0];

            this.state.sessionId = result.session_id;
            this.addSessionToSidebar(result.session_id, title, '', false);
            this.setCourseLock(false); // CHANGED: creating a chat no longer locks the course — only sending a message does

            return { sessionId: result.session_id, title };
        },

        scrollToBottom() {
            if (!this.shouldAutoScroll) return;
            const container = document.getElementById('ai-messages-container');
            container.scrollTop = container.scrollHeight;
        },

        initMarkdown() {
            if (window.marked) window.marked.setOptions({ breaks: true, gfm: true });
        },

        updateUIState() {
            const input = document.getElementById('ai-message-input');
            const sendBtn = document.getElementById('ai-send-btn');
            const isStreaming = this.state.isStreaming;
            if (input) input.disabled = isStreaming;
            if (sendBtn) sendBtn.disabled = isStreaming;
        },

        bindUI() {
            const sendBtn = document.getElementById('ai-send-btn');
            const input = document.getElementById('ai-message-input');
            const stopBtn = document.getElementById('ai-stop-btn');

            input.addEventListener('input', () => {
                input.style.height = 'auto';
                input.style.height = Math.min(input.scrollHeight, 140) + 'px';
            });

            const send = () => {
                const message = input.value.trim();
                if (!message) return;
                input.value = '';
                input.style.height = 'auto';
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
                stopBtn.addEventListener('click', async () => {
                    if (!this.state.controller) return;

                    this.state.controller.abort();
                    this.state.isStreaming = false;
                    this.updateUIState();
                    document.getElementById('ai-send-btn').style.display = 'flex';
                    document.getElementById('ai-stop-btn').style.display = 'none';

                    const partial = this.state.partialText;
                    const sessionId = this.state.sessionId;

                    if (partial && partial.trim() && sessionId) {
                        try {
                            await Ajax.call([{
                                methodname: 'local_ai_system_save_partial_message',
                                args: { session_id: sessionId, content: partial }
                            }])[0];
                        } catch (e) {
                            console.error('[ChatBot] Failed to persist partial response:', e);
                        }
                    }
                });
            }
        },

        async sendMessageStream(message) {
            if (this.state.isStreaming) return;

            this.state.isStreaming = true;
            this.state.partialText = '';
            this.state.controller = new AbortController();
            this.updateUIState();

            document.getElementById('ai-send-btn').style.display = 'none';
            document.getElementById('ai-stop-btn').style.display = 'flex';

            this.appendMessage('user', message);
            const bubble = this.createAssistantBubble();
            let fullText = '';

            await this.ensureSession();
            this.setCourseLock(true); // CHANGED: course is locked exactly when a message is actually sent

            try {
                const response = await fetch(
                    M.cfg.wwwroot + '/local/ai_system/ajax/stream.php',
                    {
                        method: 'POST',
                        signal: this.state.controller.signal,
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
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

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();

                    for (let line of lines) {
                        line = line.trim();
                        if (!line.startsWith('data:')) continue;

                        const raw = line.replace(/^data:\s?/, '');
                        if (raw === '[DONE]') continue;

                        let parsed;
                        try {
                            parsed = JSON.parse(raw);
                        } catch (err) {
                            console.error('[ChatBot] Failed to parse SSE payload, skipping:', raw, err);
                            continue;
                        }

                        if (parsed.title !== undefined) {
                            this.applyGeneratedTitle(parsed.title);
                            continue;
                        }

                        const token = parsed.token;
                        fullText += token;
                        this.state.partialText = fullText;

                        try {
                            bubble.innerHTML = window.marked ? window.marked.parse(fullText) : fullText;
                        } catch (err) {
                            bubble.innerText = fullText;
                        }

                        this.scrollToBottom();
                    }
                }
            } catch (e) {
                console.error(e);
            } finally {
                this.state.isStreaming = false;
                this.state.controller = null;
                this.updateUIState();

                try {
                    bubble.innerHTML = window.marked ? window.marked.parse(fullText || '') : fullText;
                } catch (err) {
                    bubble.innerText = fullText;
                }

                const timeEl = document.getElementById('ai-streaming-time');
                if (timeEl) {
                    timeEl.textContent = this.formatTime(new Date());
                    timeEl.removeAttribute('id');
                }

                const actionsEl = document.getElementById('ai-streaming-actions');
                if (actionsEl) {
                    this.bindMessageActions(actionsEl.closest('.ai-message'));
                    actionsEl.removeAttribute('id');
                }

                document.getElementById('ai-send-btn').style.display = 'flex';
                document.getElementById('ai-stop-btn').style.display = 'none';
                this.scrollToBottom();
            }
        },

        applyGeneratedTitle(title) {
            if (!title || !this.state.sessionId) return;

            const chatTitle = document.getElementById('ai-chat-title');
            if (chatTitle) chatTitle.textContent = title;

            const sidebarTitleEl = document.querySelector(
                `.ai-session-item[data-session-id="${this.state.sessionId}"] .ai-session-title`
            );
            if (sidebarTitleEl) sidebarTitleEl.textContent = title;
        },

        messageActionsHtml(role) {
            if (role === 'user') {
                return `<button class="ai-msg-action-btn ai-msg-action-edit" aria-label="Edit"><i class="fa fa-pencil"></i></button>`;
            }
            return `
                <button class="ai-msg-action-btn ai-msg-action-copy" aria-label="Copy"><i class="fa fa-clone"></i></button>
                <button class="ai-msg-action-btn ai-msg-action-regen" aria-label="Regenerate"><i class="fa fa-refresh"></i></button>
                <button class="ai-msg-action-btn ai-msg-action-up" aria-label="Good response"><i class="fa fa-thumbs-o-up"></i></button>
                <button class="ai-msg-action-btn ai-msg-action-down" aria-label="Bad response"><i class="fa fa-thumbs-o-down"></i></button>
            `;
        },

        appendMessage(role, content, createdAt) {
            const container = document.getElementById('ai-messages-container');

            const wrap = document.createElement('div');
            wrap.className = `ai-message ai-message--${role}`;

            const bubbleWrap = document.createElement('div');
            bubbleWrap.className = 'ai-bubble-wrap';

            const bubble = document.createElement('div');
            bubble.className = 'ai-message-bubble';

            const text = document.createElement('div');
            text.className = 'ai-message-content';
            text.innerHTML = window.marked.parse(content || '');

            const meta = document.createElement('div');
            meta.className = 'ai-message-meta';

            const time = document.createElement('span');
            time.className = 'ai-message-time';
            time.textContent = createdAt ? this.formatTime(new Date(createdAt * 1000)) : this.formatTime(new Date());

            const actions = document.createElement('div');
            actions.className = 'ai-message-actions';
            actions.innerHTML = this.messageActionsHtml(role);

            meta.appendChild(time);
            meta.appendChild(actions);

            bubble.appendChild(text);
            bubbleWrap.appendChild(bubble);
            bubbleWrap.appendChild(meta);
            wrap.appendChild(bubbleWrap);
            container.appendChild(wrap);

            this.bindMessageActions(wrap);
            this.scrollToBottom();
        },

        createAssistantBubble() {
            const container = document.getElementById('ai-messages-container');

            const wrap = document.createElement('div');
            wrap.className = 'ai-message ai-message--assistant';

            const bubbleWrap = document.createElement('div');
            bubbleWrap.className = 'ai-bubble-wrap';

            const bubble = document.createElement('div');
            bubble.className = 'ai-message-bubble';

            const text = document.createElement('div');
            text.className = 'ai-message-content';

            const meta = document.createElement('div');
            meta.className = 'ai-message-meta';

            const time = document.createElement('span');
            time.className = 'ai-message-time';
            time.id = 'ai-streaming-time';

            const actions = document.createElement('div');
            actions.className = 'ai-message-actions';
            actions.id = 'ai-streaming-actions';
            actions.innerHTML = this.messageActionsHtml('assistant');

            meta.appendChild(time);
            meta.appendChild(actions);

            bubble.appendChild(text);
            bubbleWrap.appendChild(bubble);
            bubbleWrap.appendChild(meta);
            wrap.appendChild(bubbleWrap);
            container.appendChild(wrap);

            return text;
        },

        bindNewSession() {
            const btn = document.querySelector('.ai-chatbot-new-session');
            if (!btn) return;

            btn.addEventListener('click', async () => {
                const { title } = await this.createNewSession();
                document.getElementById('ai-messages-container').innerHTML = '';
                document.getElementById('ai-chat-title').textContent = title;
            });
        },
    };

    return {
        init: (sessionId, courseId) => ChatBot.init(sessionId, courseId)
    };
});
