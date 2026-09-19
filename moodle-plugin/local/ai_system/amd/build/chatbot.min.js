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
            pinned: {},
            pendingImage: null // { file, dataUrl } — set while an image is attached but not yet sent
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
            this.bindAttachImage();
            this.bindImageLightbox();
            this.bindGlobalDelegation();
            this.bindContextMenuActions();
            this.bindRenamePopup();
            this.groupSessionsByDate();
            this.bindNewSession();
            this.bindLanguagePicker();
            this.bindHeaderPin();
            this.bindExportPdf();
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
            const weekContainer = document.getElementById('ai-sb-week');
            const monthContainer = document.getElementById('ai-sb-month');
            const previousContainer = document.getElementById('ai-sb-previous');
            const weekGroup = document.getElementById('ai-sb-week-group');
            const monthGroup = document.getElementById('ai-sb-month-group');
            const previousGroup = document.getElementById('ai-sb-previous-group');
            if (!todayContainer || !weekContainer || !monthContainer || !previousContainer) return;

            const now = new Date();

            const midnight = new Date(now);
            midnight.setHours(0, 0, 0, 0);
            const todayCutoff = Math.floor(midnight.getTime() / 1000);

            // Start of week = last Monday 00:00 (ISO-ish week, ignores locale
            // week-start settings — Monday everywhere for consistency).
            const weekStart = new Date(midnight);
            const dayOfWeek = (weekStart.getDay() + 6) % 7; // Mon=0 ... Sun=6
            weekStart.setDate(weekStart.getDate() - dayOfWeek);
            const weekCutoff = Math.floor(weekStart.getTime() / 1000);

            const monthStart = new Date(now.getFullYear(), now.getMonth(), 1, 0, 0, 0, 0);
            const monthCutoff = Math.floor(monthStart.getTime() / 1000);

            let movedWeek = false;
            let movedMonth = false;
            let movedOlder = false;

            Array.from(todayContainer.children).forEach(el => {
                const ts = parseInt(el.dataset.createdAt, 10);
                if (!ts || ts >= todayCutoff) return; // stays in Today

                if (ts >= weekCutoff) {
                    weekContainer.appendChild(el);
                    movedWeek = true;
                } else if (ts >= monthCutoff) {
                    monthContainer.appendChild(el);
                    movedMonth = true;
                } else {
                    previousContainer.appendChild(el);
                    movedOlder = true;
                }
            });

            if (movedWeek && weekGroup) weekGroup.style.display = '';
            if (movedMonth && monthGroup) monthGroup.style.display = '';
            if (movedOlder && previousGroup) previousGroup.style.display = '';
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

            scope.querySelectorAll('.ai-msg-action-edit').forEach(btn => {
                if (btn.dataset.bound) return;
                btn.dataset.bound = '1';
                btn.addEventListener('click', () => {
                    const wrap = btn.closest('.ai-message');
                    if (wrap) this.enterEditMode(wrap);
                });
            });

            scope.querySelectorAll('.ai-msg-action-regen').forEach(btn => {
                if (btn.dataset.bound) return;
                btn.dataset.bound = '1';
                btn.addEventListener('click', () => {
                    const wrap = btn.closest('.ai-message');
                    if (wrap) this.regenerateMessage(wrap);
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
        // IMAGE ATTACHMENT
        // =========================
        MAX_IMAGE_BYTES: 8 * 1024 * 1024, // 8 MB — keep in sync with stream.php
        ALLOWED_IMAGE_TYPES: ['image/jpeg', 'image/png', 'image/webp', 'image/gif'],

        bindAttachImage() {
            const attachBtn = document.getElementById('ai-attach-btn');
            const fileInput = document.getElementById('ai-image-input');
            const removeBtn = document.getElementById('ai-image-preview-remove');
            if (!attachBtn || !fileInput) return;

            attachBtn.addEventListener('click', () => {
                if (this.state.isStreaming) return;
                fileInput.click();
            });

            fileInput.addEventListener('change', () => {
                const file = fileInput.files?.[0];
                fileInput.value = ''; // allow re-selecting the same file later
                if (!file) return;
                this.setPendingImage(file);
            });

            removeBtn?.addEventListener('click', () => this.clearPendingImage());
        },

        setPendingImage(file) {
            if (!this.ALLOWED_IMAGE_TYPES.includes(file.type)) {
                window.alert('Please choose a JPEG, PNG, WEBP or GIF image.');
                return;
            }
            if (file.size > this.MAX_IMAGE_BYTES) {
                window.alert('Image is too large (max 8 MB).');
                return;
            }

            const reader = new FileReader();
            reader.onload = () => {
                this.state.pendingImage = { file, dataUrl: reader.result };
                this.renderImagePreview();
            };
            reader.readAsDataURL(file);
        },

        clearPendingImage() {
            this.state.pendingImage = null;
            this.renderImagePreview();
        },

        renderImagePreview() {
            const wrap = document.getElementById('ai-image-preview');
            const thumb = document.getElementById('ai-image-preview-thumb');
            const name = document.getElementById('ai-image-preview-name');
            if (!wrap || !thumb || !name) return;

            const pending = this.state.pendingImage;
            if (!pending) {
                wrap.classList.add('hidden');
                thumb.src = '';
                return;
            }

            thumb.src = pending.dataUrl;
            name.textContent = pending.file.name;
            wrap.classList.remove('hidden');
        },

        // =========================
        // IMAGE LIGHTBOX (click a chat image to open it full-size)
        // =========================
        bindImageLightbox() {
            const container = document.getElementById('ai-messages-container');
            if (!container) return;

            // Event delegation: works for images that exist now AND ones
            // added later (streamed replies, future history loads).
            container.addEventListener('click', (e) => {
                const img = e.target.closest('.ai-message-image');
                if (img) this.openImageLightbox(img.src, img.alt);
            });
        },

        ensureLightboxEl() {
            let overlay = document.getElementById('ai-lightbox-overlay');
            if (overlay) return overlay;

            overlay = document.createElement('div');
            overlay.id = 'ai-lightbox-overlay';
            overlay.className = 'ai-lightbox-overlay';
            overlay.innerHTML = `
                <button class="ai-lightbox-close" aria-label="Close">
                    <i class="fa fa-times" aria-hidden="true"></i>
                </button>
                <img class="ai-lightbox-img" id="ai-lightbox-img" src="" alt="">
            `;
            document.body.appendChild(overlay);

            overlay.addEventListener('click', (e) => {
                if (e.target === overlay || e.target.closest('.ai-lightbox-close')) {
                    this.closeImageLightbox();
                }
            });

            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') this.closeImageLightbox();
            });

            return overlay;
        },

        openImageLightbox(src, alt) {
            const overlay = this.ensureLightboxEl();
            const img = document.getElementById('ai-lightbox-img');
            img.src = src;
            img.alt = alt || '';
            overlay.classList.add('open');
        },

        closeImageLightbox() {
            const overlay = document.getElementById('ai-lightbox-overlay');
            if (overlay) overlay.classList.remove('open');
        },

        // =========================
        // EXPORT TO PDF
        // =========================
        bindExportPdf() {
            const btn = document.getElementById('ai-export-pdf-btn');
            if (!btn) return;

            btn.addEventListener('click', () => {
                if (btn.disabled) return;
                this.exportChatToPdf();
            });
        },

        // Lazily loads html2canvas + jsPDF from CDN, once, and caches the
        // in-flight promise so rapid double-clicks don't inject the
        // <script> tags twice.
        //
        // IMPORTANT: Moodle runs RequireJS on every page. The UMD builds of
        // html2canvas/jsPDF detect `define.amd` and, when present, register
        // themselves as an anonymous AMD module instead of attaching to
        // `window` — so `window.html2canvas` stays undefined even though
        // the script loaded fine. We work around this by temporarily
        // hiding `window.define` while the script executes, forcing it
        // down the "plain browser global" branch of its UMD wrapper.
        ensureExportLibs() {
            if (this._exportLibsPromise) return this._exportLibsPromise;

            const loadGlobalScript = (src) => new Promise((resolve, reject) => {
                const originalDefine = window.define;
                window.define = undefined; // hide AMD from the UMD wrapper

                const el = document.createElement('script');
                el.src = src;
                el.onload = () => {
                    window.define = originalDefine;
                    resolve();
                };
                el.onerror = () => {
                    window.define = originalDefine;
                    reject(new Error('Failed to load script: ' + src));
                };
                document.head.appendChild(el);
            });

            this._exportLibsPromise = (async () => {
                if (typeof window.html2canvas !== 'function') {
                    await loadGlobalScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
                }
                if (!window.jspdf || typeof window.jspdf.jsPDF !== 'function') {
                    await loadGlobalScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');
                }
                if (typeof window.html2canvas !== 'function' || typeof window.jspdf?.jsPDF !== 'function') {
                    throw new Error('PDF export libraries failed to initialize on window.');
                }
            })().catch((err) => {
                // Don't cache a permanently-broken promise — allow retry
                // on the next click (e.g. after a transient network issue).
                this._exportLibsPromise = null;
                throw err;
            });

            return this._exportLibsPromise;
        },

        // Builds an off-screen, print-friendly clone of the conversation
        // (forced light background, no hover actions) so the exported PDF
        // looks the same regardless of dark/light theme, and renders any
        // language/script correctly since it's captured as an image rather
        // than drawn with jsPDF's built-in (Latin-only) fonts.
        buildExportNode(title) {
            const source = document.getElementById('ai-messages-container');

            const wrapper = document.createElement('div');
            wrapper.className = 'ai-pdf-export-wrapper';

            const heading = document.createElement('div');
            heading.className = 'ai-pdf-export-title';
            heading.textContent = title;

            const dateLine = document.createElement('div');
            dateLine.className = 'ai-pdf-export-date';
            dateLine.textContent = new Date().toLocaleString();

            const clone = source.cloneNode(true);
            clone.classList.add('ai-pdf-export-clone');
            clone.querySelectorAll('.ai-message-actions').forEach(el => el.remove());
            clone.removeAttribute('id');

            wrapper.appendChild(heading);
            wrapper.appendChild(dateLine);
            wrapper.appendChild(clone);
            document.body.appendChild(wrapper);

            return wrapper;
        },

        async exportChatToPdf() {
            const btn = document.getElementById('ai-export-pdf-btn');
            const icon = btn?.querySelector('i');
            const container = document.getElementById('ai-messages-container');

            if (!container || !container.children.length) {
                window.alert('This chat has no messages to export yet.');
                return;
            }

            const originalIconClass = icon?.className;
            if (btn) btn.disabled = true;
            if (icon) icon.className = 'fa fa-spinner fa-spin';

            let exportNode = null;

            try {
                await this.ensureExportLibs();

                const title = document.getElementById('ai-chat-title')?.textContent.trim()
                    || 'SDG-Campus AI Chatbot';

                exportNode = this.buildExportNode(title);

                const canvas = await window.html2canvas(exportNode, {
                    scale: 2,
                    backgroundColor: '#ffffff',
                    useCORS: true
                });

                const { jsPDF } = window.jspdf;
                const pdf = new jsPDF('p', 'mm', 'a4');

                const pageWidth = pdf.internal.pageSize.getWidth();
                const pageHeight = pdf.internal.pageSize.getHeight();
                const margin = 10;
                const usableWidth = pageWidth - margin * 2;
                const usableHeight = pageHeight - margin * 2;
                const imgHeight = (canvas.height * usableWidth) / canvas.width;

                const imgData = canvas.toDataURL('image/png');

                let heightLeft = imgHeight;
                let position = margin;

                pdf.addImage(imgData, 'PNG', margin, position, usableWidth, imgHeight);
                heightLeft -= usableHeight;

                while (heightLeft > 0) {
                    position = margin - (imgHeight - heightLeft);
                    pdf.addPage();
                    pdf.addImage(imgData, 'PNG', margin, position, usableWidth, imgHeight);
                    heightLeft -= usableHeight;
                }

                const safeTitle = title
                    .replace(/[^\p{L}\p{N}_\- ]+/gu, '')
                    .trim()
                    .replace(/\s+/g, '_')
                    .slice(0, 60) || 'chat';

                pdf.save(`${safeTitle}.pdf`);
            } catch (e) {
                console.error('[ChatBot] PDF export failed:', e);
                window.alert('Sorry, something went wrong while generating the PDF. Please try again.');
            } finally {
                if (exportNode) exportNode.remove();
                if (btn) btn.disabled = false;
                if (icon) icon.className = originalIconClass;
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
                        messages.forEach(msg => this.appendMessage(msg.role, msg.content, msg.created_at, msg.image_url, msg.id));
                        await this.loadVersionNav();

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
            messages.forEach(msg => this.appendMessage(msg.role, msg.content, msg.created_at, msg.image_url, msg.id));
            this.loadVersionNav();

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
                if (!message && !this.state.pendingImage) return;
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

            const pendingImage = this.state.pendingImage;

            this.state.isStreaming = true;
            this.state.partialText = '';
            this.state.controller = new AbortController();
            this.updateUIState();

            document.getElementById('ai-send-btn').style.display = 'none';
            document.getElementById('ai-stop-btn').style.display = 'flex';

            const userWrap = this.appendMessage('user', message, null, pendingImage?.dataUrl);
            this.clearPendingImage();
            const bubble = this.createAssistantBubble();

            await this.ensureSession();
            this.setCourseLock(true); // CHANGED: course is locked exactly when a message is actually sent

            try {
                const body = new FormData();
                body.append('session_id', this.state.sessionId);
                body.append('message', message);
                body.append('sesskey', M.cfg.sesskey);
                if (pendingImage) {
                    body.append('image', pendingImage.file, pendingImage.file.name);
                }

                const response = await fetch(
                    M.cfg.wwwroot + '/local/ai_system/ajax/stream.php',
                    {
                        method: 'POST',
                        signal: this.state.controller.signal,
                        // NOTE: no Content-Type header here — the browser sets the
                        // correct multipart/form-data boundary automatically for FormData.
                        body: body
                    }
                );

                await this.consumeStream(response, bubble, (meta) => {
                    if (meta.user_message_id) userWrap.dataset.messageId = meta.user_message_id;
                    const assistantWrap = bubble.closest('.ai-message');
                    if (assistantWrap && meta.assistant_message_id) {
                        assistantWrap.dataset.messageId = meta.assistant_message_id;
                    }
                });
            } catch (e) {
                console.error(e);
            } finally {
                this.finishStreamingUI(bubble);
            }
        },

        // =========================
        // SHARED SSE CONSUMER — used by send / edit / regenerate, they all
        // speak the same "data: {token|title|meta|error}\n\n ... [DONE]"
        // protocol (see stream.php / edit_stream.php / regenerate_stream.php).
        // =========================
        async consumeStream(response, bubbleTextEl, onMeta) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let fullText = '';

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

                    if (parsed.meta !== undefined) {
                        if (onMeta) onMeta(parsed.meta);
                        continue;
                    }

                    if (parsed.error !== undefined) {
                        console.error('[ChatBot] Stream error:', parsed.error);
                        continue;
                    }

                    const token = parsed.token;
                    fullText += token;
                    this.state.partialText = fullText;

                    try {
                        bubbleTextEl.innerHTML = window.marked ? window.marked.parse(fullText) : fullText;
                    } catch (err) {
                        bubbleTextEl.innerText = fullText;
                    }

                    this.scrollToBottom();
                }
            }

            try {
                bubbleTextEl.innerHTML = window.marked ? window.marked.parse(fullText || '') : fullText;
            } catch (err) {
                bubbleTextEl.innerText = fullText;
            }

            const wrap = bubbleTextEl.closest('.ai-message');
            if (wrap) wrap.dataset.rawContent = fullText;

            return fullText;
        },

        finishStreamingUI(bubbleTextEl) {
            this.state.isStreaming = false;
            this.state.controller = null;
            this.updateUIState();

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
        },

        // =========================
        // EDIT A USER MESSAGE
        // =========================
        enterEditMode(wrap) {
            if (this.state.isStreaming) return;
            if (wrap.querySelector('.ai-edit-wrap')) return; // already editing

            const bubble = wrap.querySelector('.ai-message-bubble');
            const contentEl = wrap.querySelector('.ai-message-content');
            const metaEl = wrap.querySelector('.ai-message-meta');
            if (!bubble || !contentEl) return;

            const rawContent = wrap.dataset.rawContent || contentEl.innerText;

            contentEl.style.display = 'none';
            if (metaEl) metaEl.style.display = 'none';

            const editWrap = document.createElement('div');
            editWrap.className = 'ai-edit-wrap';
            editWrap.innerHTML = `
                <textarea class="ai-edit-textarea"></textarea>
                <div class="ai-edit-actions">
                    <button type="button" class="btn btn-secondary btn-sm ai-edit-cancel">Cancel</button>
                    <button type="button" class="btn btn-primary btn-sm ai-edit-save">Save &amp; submit</button>
                </div>
            `;
            bubble.appendChild(editWrap);

            const textarea = editWrap.querySelector('.ai-edit-textarea');
            textarea.value = rawContent;
            textarea.focus();
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 300) + 'px';
            textarea.addEventListener('input', () => {
                textarea.style.height = 'auto';
                textarea.style.height = Math.min(textarea.scrollHeight, 300) + 'px';
            });

            const exitEditMode = () => {
                editWrap.remove();
                contentEl.style.display = '';
                if (metaEl) metaEl.style.display = '';
            };

            editWrap.querySelector('.ai-edit-cancel').addEventListener('click', exitEditMode);

            editWrap.querySelector('.ai-edit-save').addEventListener('click', () => {
                const newContent = textarea.value.trim();
                if (!newContent) return;
                exitEditMode();
                this.submitEdit(wrap, newContent);
            });
        },

        async submitEdit(wrap, newContent) {
            if (this.state.isStreaming) return;

            const messageId = wrap.dataset.messageId;
            const sessionId = this.state.sessionId;
            if (!messageId || !sessionId) {
                console.error('[ChatBot] Cannot edit: missing message id or session id.');
                return;
            }

            // Everything after this message belonged to the branch we're
            // about to replace — drop it from view (it stays in the DB,
            // reachable again if the user navigates back to the old
            // version via the "< i/N >" arrows).
            this.removeMessagesAfter(wrap);

            const contentEl = wrap.querySelector('.ai-message-content');
            contentEl.innerHTML = window.marked ? window.marked.parse(newContent) : newContent;
            wrap.dataset.rawContent = newContent;

            this.state.isStreaming = true;
            this.state.controller = new AbortController();
            this.updateUIState();
            document.getElementById('ai-send-btn').style.display = 'none';
            document.getElementById('ai-stop-btn').style.display = 'flex';

            const bubble = this.createAssistantBubble();

            try {
                const response = await fetch(
                    M.cfg.wwwroot + '/local/ai_system/ajax/edit_stream.php',
                    {
                        method: 'POST',
                        signal: this.state.controller.signal,
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: 'session_id=' + encodeURIComponent(sessionId)
                            + '&message_id=' + encodeURIComponent(messageId)
                            + '&content=' + encodeURIComponent(newContent)
                            + '&sesskey=' + encodeURIComponent(M.cfg.sesskey)
                    }
                );

                await this.consumeStream(response, bubble, (meta) => {
                    if (meta.user_message_id) wrap.dataset.messageId = meta.user_message_id;
                    const assistantWrap = bubble.closest('.ai-message');
                    if (assistantWrap && meta.assistant_message_id) {
                        assistantWrap.dataset.messageId = meta.assistant_message_id;
                    }
                    if (meta.version_count > 1) {
                        this.renderVersionNav(meta.user_message_id, meta.version_index, meta.version_count, meta.sibling_ids);
                    }
                });
            } catch (e) {
                console.error('[ChatBot] Edit failed:', e);
            } finally {
                this.finishStreamingUI(bubble);
            }
        },

        // =========================
        // REGENERATE AN ASSISTANT REPLY
        // =========================
        async regenerateMessage(wrap) {
            if (this.state.isStreaming) return;

            const messageId = wrap.dataset.messageId;
            const sessionId = this.state.sessionId;
            if (!messageId || !sessionId) {
                console.error('[ChatBot] Cannot regenerate: missing message id or session id.');
                return;
            }

            this.removeMessagesAfter(wrap);
            wrap.remove();

            this.state.isStreaming = true;
            this.state.controller = new AbortController();
            this.updateUIState();
            document.getElementById('ai-send-btn').style.display = 'none';
            document.getElementById('ai-stop-btn').style.display = 'flex';

            const bubble = this.createAssistantBubble();

            try {
                const response = await fetch(
                    M.cfg.wwwroot + '/local/ai_system/ajax/regenerate_stream.php',
                    {
                        method: 'POST',
                        signal: this.state.controller.signal,
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: 'session_id=' + encodeURIComponent(sessionId)
                            + '&message_id=' + encodeURIComponent(messageId)
                            + '&sesskey=' + encodeURIComponent(M.cfg.sesskey)
                    }
                );

                await this.consumeStream(response, bubble, (meta) => {
                    const assistantWrap = bubble.closest('.ai-message');
                    if (assistantWrap && meta.assistant_message_id) {
                        assistantWrap.dataset.messageId = meta.assistant_message_id;
                    }
                    if (meta.version_count > 1) {
                        this.renderVersionNav(meta.assistant_message_id, meta.version_index, meta.version_count, meta.sibling_ids);
                    }
                });
            } catch (e) {
                console.error('[ChatBot] Regenerate failed:', e);
            } finally {
                this.finishStreamingUI(bubble);
            }
        },

        removeMessagesAfter(wrap) {
            let sib = wrap.nextElementSibling;
            while (sib) {
                const next = sib.nextElementSibling;
                sib.remove();
                sib = next;
            }
        },

        // =========================
        // VERSION NAVIGATION ("< i/N >")
        // =========================
        renderVersionNav(messageId, versionIndex, versionCount, siblingIds) {
            const wrap = document.querySelector(`.ai-message[data-message-id="${messageId}"]`);
            if (!wrap) return;
            const meta = wrap.querySelector('.ai-message-meta');
            if (!meta) return;

            let nav = meta.querySelector('.ai-version-nav');

            if (!versionCount || versionCount <= 1) {
                if (nav) nav.remove();
                return;
            }

            if (!nav) {
                nav = document.createElement('div');
                nav.className = 'ai-version-nav';
                meta.insertBefore(nav, meta.firstChild);
            }

            nav.innerHTML = `
                <button type="button" class="ai-version-prev" aria-label="Previous version" ${versionIndex <= 1 ? 'disabled' : ''}>
                    <i class="fa fa-chevron-left"></i>
                </button>
                <span class="ai-version-label">${versionIndex}/${versionCount}</span>
                <button type="button" class="ai-version-next" aria-label="Next version" ${versionIndex >= versionCount ? 'disabled' : ''}>
                    <i class="fa fa-chevron-right"></i>
                </button>
            `;
            nav.dataset.siblingIds = JSON.stringify(siblingIds || []);
            nav.dataset.currentIndex = versionIndex;

            if (!nav.dataset.bound) {
                nav.dataset.bound = '1';
                nav.addEventListener('click', (e) => {
                    const prevBtn = e.target.closest('.ai-version-prev');
                    const nextBtn = e.target.closest('.ai-version-next');
                    if ((!prevBtn && !nextBtn) || this.state.isStreaming) return;

                    const ids = JSON.parse(nav.dataset.siblingIds || '[]');
                    const currentIdx = parseInt(nav.dataset.currentIndex, 10) - 1; // 0-based
                    const targetIdx = prevBtn ? currentIdx - 1 : currentIdx + 1;
                    if (targetIdx < 0 || targetIdx >= ids.length) return;

                    this.activateVersion(ids[targetIdx]);
                });
            }
        },

        async activateVersion(messageId) {
            const sessionId = this.state.sessionId;
            if (!sessionId || this.state.isStreaming) return;

            try {
                await fetch(M.cfg.wwwroot + '/local/ai_system/ajax/activate_version.php', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'session_id=' + encodeURIComponent(sessionId)
                        + '&message_id=' + encodeURIComponent(messageId)
                        + '&sesskey=' + encodeURIComponent(M.cfg.sesskey)
                });
                await this.refreshMessages();
            } catch (e) {
                console.error('[ChatBot] Failed to switch version:', e);
            }
        },

        // Re-fetches the active conversation thread and re-renders it —
        // same shape as loadSession(), minus touching the sidebar/title.
        async refreshMessages() {
            const sessionId = this.state.sessionId;
            if (!sessionId) return;

            const result = await Ajax.call([{
                methodname: 'local_ai_system_get_messages',
                args: { session_id: sessionId }
            }])[0];

            const messages = Array.isArray(result) ? result : (result.messages ?? []);

            const container = document.getElementById('ai-messages-container');
            container.innerHTML = '';
            messages.forEach(msg => this.appendMessage(msg.role, msg.content, msg.created_at, msg.image_url, msg.id));
            await this.loadVersionNav();
        },

        async loadVersionNav() {
            const sessionId = this.state.sessionId;
            if (!sessionId) return;

            try {
                const resp = await fetch(M.cfg.wwwroot + '/local/ai_system/ajax/versions_meta.php', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'session_id=' + encodeURIComponent(sessionId)
                        + '&sesskey=' + encodeURIComponent(M.cfg.sesskey)
                });
                const meta = await resp.json();
                Object.entries(meta).forEach(([messageId, info]) => {
                    this.renderVersionNav(messageId, info.version_index, info.version_count, info.sibling_ids);
                });
            } catch (e) {
                console.error('[ChatBot] Failed to load version metadata:', e);
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
            `;
        },

        appendMessage(role, content, createdAt, imageDataUrl, messageId) {
            const container = document.getElementById('ai-messages-container');

            const wrap = document.createElement('div');
            wrap.className = `ai-message ai-message--${role}`;
            if (messageId) wrap.dataset.messageId = messageId;
            wrap.dataset.rawContent = content || '';

            const bubbleWrap = document.createElement('div');
            bubbleWrap.className = 'ai-bubble-wrap';

            const bubble = document.createElement('div');
            bubble.className = 'ai-message-bubble';

            if (imageDataUrl) {
                const img = document.createElement('img');
                img.className = 'ai-message-image';
                img.src = imageDataUrl;
                img.alt = 'Attached image';
                bubble.appendChild(img);
            }

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
            return wrap;
        },

        createAssistantBubble() {
            const container = document.getElementById('ai-messages-container');

            const wrap = document.createElement('div');
            wrap.className = 'ai-message ai-message--assistant';
            wrap.dataset.rawContent = '';

            const bubbleWrap = document.createElement('div');
            bubbleWrap.className = 'ai-bubble-wrap';

            const bubble = document.createElement('div');
            bubble.className = 'ai-message-bubble';

            const text = document.createElement('div');
            text.className = 'ai-message-content';
            text.innerHTML = '<span class="ai-typing-indicator"><span></span><span></span><span></span></span>';

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
