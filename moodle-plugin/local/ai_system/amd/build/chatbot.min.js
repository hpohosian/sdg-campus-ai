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
            translationRun: 0, // bumped on every (re)render: late translations of an older render are dropped
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
            this.bindSidebarSearch();
            this.bindSuggestions();
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

        // Lazily loads html2canvas + jsPDF (bundled in thirdparty/), once, and caches the
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
                // Bundled with the plugin (thirdpartylibs.xml), not from a CDN.
                const base = (window.M && window.M.cfg ? window.M.cfg.wwwroot : '') + '/local/ai_system/thirdparty';
                if (typeof window.html2canvas !== 'function') {
                    await loadGlobalScript(base + '/html2canvas/html2canvas.min.js');
                }
                if (!window.jspdf || typeof window.jspdf.jsPDF !== 'function') {
                    await loadGlobalScript(base + '/jspdf/jspdf.umd.min.js');
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

                option.addEventListener('click', async (e) => {
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

                    // The picker is only clickable (not disabled) while the
                    // currently open chat is still empty. If that chat was
                    // already created on the backend (e.g. via "New Chat"),
                    // its course_id was fixed at creation time and never
                    // updates on its own — patch it now, or every message
                    // sent afterwards keeps using the old course for RAG.
                    if (this.state.sessionId) {
                        try {
                            await Ajax.call([{
                                methodname: 'local_ai_system_update_session',
                                args: { session_id: this.state.sessionId, course_id: courseId }
                            }])[0];
                        } catch (err) {
                            console.error('[ChatBot] Failed to update session course_id:', err);
                        }
                    }
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

                        // Shows the chat at once (cached translations, originals
                        // for the rest), then translates message by message.
                        await this.loadThread(this.state.sessionId);

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
        // SOURCE CARDS
        // RAG_SYSTEM_PROMPT makes the model end an answer with
        // "Source: <file link>, from <course link>". That paragraph is found
        // language-independently (a short paragraph containing a link to
        // /pluginfile.php/) and replaced by cards. The word before the first
        // link ("Quelle", "Source", ...) becomes the small label above them.
        // =========================
        renderSourceCards(contentEl) {
            if (!contentEl || contentEl.querySelector('.ai-sources')) return;

            // Source links: files (pluginfile.php), activities such as pages and
            // books (/mod/...), and course sections / labels (course/view.php
            // with an anchor). A course link WITHOUT anchor is the course part.
            const FILE_SEL = 'a[href*="/pluginfile.php/"], a[href*="/mod/"], '
                + 'a[href*="/course/view.php"][href*="#section-"], a[href*="/course/view.php"][href*="#label-"]';
            const para = Array.from(contentEl.querySelectorAll(':scope > p')).reverse().find(p => {
                if (!p.querySelector(FILE_SEL)) return false;
                let rest = p.textContent;
                p.querySelectorAll('a').forEach(a => { rest = rest.replace(a.textContent, ''); });
                return rest.replace(/[\s.,:;\u2013\u2014-]/g, '').length <= 40;
            });
            if (!para) return;

            const files = Array.from(para.querySelectorAll(FILE_SEL));
            const courses = Array.from(para.querySelectorAll('a[href*="/course/view.php"]'))
                .filter(a => !a.matches(FILE_SEL));

            const firstLink = para.querySelector('a');
            const fullText = para.textContent;
            let label = fullText.slice(0, fullText.indexOf(firstLink.textContent)).replace(/[:\s]+$/, '').trim();
            if (label.length > 24) label = '';

            const iconFor = (name, href) => {
                if (/\/mod\/book\//.test(href)) return 'fa-book';
                if (/\/mod\//.test(href) || /#(section|label)-/.test(href)) return 'fa-file-text-o';
                const ext = (name.split('.').pop() || '').toLowerCase();
                return ({
                    pdf: 'fa-file-pdf-o', doc: 'fa-file-word-o', docx: 'fa-file-word-o',
                    ppt: 'fa-file-powerpoint-o', pptx: 'fa-file-powerpoint-o',
                    xls: 'fa-file-excel-o', xlsx: 'fa-file-excel-o'
                })[ext] || 'fa-file-text-o';
            };

            const list = document.createElement('div');
            list.className = 'ai-sources-list';

            // One card per source: the same file cited for several pages
            // (file.pdf#page=2, file.pdf#page=3) becomes ONE card "S. 2–3".
            const pageWord = /quelle/i.test(label) ? 'S.'
                : /источник|джерело/i.test(label) ? 'с.' : 'p.';
            const formatPages = (pages) => {
                const sorted = Array.from(new Set(pages)).sort((x, y) => x - y);
                const parts = [];
                for (let k = 0; k < sorted.length; k++) {
                    let end = k;
                    while (end + 1 < sorted.length && sorted[end + 1] === sorted[end] + 1) end++;
                    parts.push(end > k ? `${sorted[k]}–${sorted[end]}` : `${sorted[k]}`);
                    k = end;
                }
                return parts.join(', ');
            };
            const groups = new Map();
            files.forEach((a, i) => {
                const href = a.getAttribute('href') || '';
                const key = href.replace(/#page=\d+$/, '');
                const pageMatch = /#page=(\d+)/.exec(href);
                let group = groups.get(key);
                if (!group) {
                    group = { a, course: courses[i] || courses[0], pages: [] };
                    groups.set(key, group);
                }
                if (pageMatch) group.pages.push(Number(pageMatch[1]));
            });

            groups.forEach((group) => {
                const a = group.a;
                let name = a.textContent.trim();
                if (!name) {
                    try { name = decodeURIComponent(a.pathname.split('/').pop() || ''); } catch (e) { name = a.pathname; }
                }
                const course = group.course;
                // The card opens the first cited page.
                const firstPage = group.pages.length ? Math.min(...group.pages) : null;

                const card = document.createElement('a');
                card.className = 'ai-source-card';
                card.href = firstPage ? a.href.replace(/#page=\d+$/, '') + '#page=' + firstPage : a.href;
                card.target = '_blank';
                card.rel = 'noopener noreferrer';

                const icon = document.createElement('i');
                icon.className = 'fa ' + iconFor(name, a.href);
                icon.setAttribute('aria-hidden', 'true');

                const text = document.createElement('span');
                text.className = 'ai-source-text';

                const nameEl = document.createElement('span');
                nameEl.className = 'ai-source-name';
                nameEl.textContent = name;
                nameEl.title = name;
                text.appendChild(nameEl);

                const pagesText = group.pages.length ? `${pageWord} ${formatPages(group.pages)}` : '';

                if (course || pagesText) {
                    const courseEl = document.createElement('span');
                    courseEl.className = 'ai-source-course';
                    courseEl.textContent = [
                        course ? course.textContent.trim() : '',
                        pagesText
                    ].filter(Boolean).join(' · ');
                    text.appendChild(courseEl);
                }

                card.appendChild(icon);
                card.appendChild(text);
                list.appendChild(card);
            });

            const box = document.createElement('div');
            box.className = 'ai-sources';
            if (label) {
                const labelEl = document.createElement('div');
                labelEl.className = 'ai-sources-label';
                labelEl.textContent = label;
                box.appendChild(labelEl);
            }
            box.appendChild(list);
            para.replaceWith(box);
        },

        // =========================
        // SIDEBAR SEARCH (client-side filter over the chats already in the sidebar)
        // =========================
        bindSidebarSearch() {
            const input = document.getElementById('ai-sb-search-input');
            const kbd = document.getElementById('ai-sb-search-kbd');
            if (!input) return;

            const isMac = /Mac|iPhone|iPad/.test(navigator.platform || '');
            if (kbd) kbd.textContent = isMac ? '\u2318K' : 'Ctrl K';

            const apply = () => {
                const q = input.value.trim().toLowerCase();
                const items = document.querySelectorAll('#ai-chatbot-layout .ai-session-item');
                let visibleInList = 0;

                items.forEach(el => {
                    const title = (el.querySelector('.ai-session-title')?.textContent || '').toLowerCase();
                    const match = !q || title.includes(q);
                    el.classList.toggle('hidden', !match);
                    if (match && !el.classList.contains('ai-session-archived')) visibleInList++;
                });

                document.querySelectorAll('#ai-chatbot-layout .ai-sb-group').forEach(group => {
                    if (!q) {
                        group.classList.remove('hidden');
                        return;
                    }
                    group.classList.toggle('hidden', !group.querySelector('.ai-session-item:not(.hidden)'));
                });

                const none = document.getElementById('ai-sb-no-results');
                if (none) none.classList.toggle('hidden', !q || visibleInList > 0);
            };

            input.addEventListener('input', apply);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    input.value = '';
                    apply();
                    input.blur();
                }
            });

            document.addEventListener('keydown', (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key && e.key.toLowerCase() === 'k') {
                    e.preventDefault();
                    input.focus();
                    input.select();
                }
            });
        },

        // =========================
        // START SCREEN SUGGESTIONS (fill the input, the user sends it)
        // =========================
        bindSuggestions() {
            document.querySelectorAll('.ai-suggest-card').forEach(card => {
                card.addEventListener('click', () => {
                    const input = document.getElementById('ai-message-input');
                    const text = card.querySelector('.ai-suggest-text')?.textContent.trim();
                    if (!input || !text) return;
                    input.value = text;
                    input.dispatchEvent(new Event('input'));
                    input.focus();
                });
            });
        },

        closeArchivePanel() {
            document.getElementById('ai-archive-dropdown')?.classList.add('hidden');
            document.getElementById('ai-archive-toggle')?.classList.remove('open');
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
            if (!archived) this.closeArchivePanel();

            this.setActiveLanguage(item?.dataset.language || '');

            const messages = await this.loadThread(sessionId, { versionNav: false });

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

            await this.loadVersionNav();

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

        // =========================
        // BUNDLED LIBRARIES LOADED ON DEMAND (thirdparty/)
        // =========================
        // Loads a script once and caches the promise. RequireJS is active on
        // Moodle pages: UMD builds would register as an anonymous AMD module
        // instead of setting window.X, so `define` is hidden while the
        // script runs.
        loadVendor(path) {
            this._vendor = this._vendor || {};
            if (this._vendor[path]) return this._vendor[path];
            const base = (window.M && window.M.cfg ? window.M.cfg.wwwroot : '') + '/local/ai_system/thirdparty/';
            this._vendor[path] = new Promise((resolve, reject) => {
                const originalDefine = window.define;
                window.define = undefined;
                const el = document.createElement('script');
                el.src = base + path;
                el.onload = () => { window.define = originalDefine; resolve(); };
                el.onerror = () => {
                    window.define = originalDefine;
                    delete this._vendor[path];          // allow a retry later
                    reject(new Error('Failed to load ' + path));
                };
                document.head.appendChild(el);
            });
            return this._vendor[path];
        },

        // =========================
        // DIAGRAMS (```mermaid) AND CHARTS (```chart) IN ANSWERS
        // =========================
        // The model writes a fenced block; marked turns it into
        // <pre><code class="language-mermaid|language-chart">. Here such
        // blocks are replaced by the drawing. While the answer is still
        // streaming the CSS shows a placeholder instead of the raw code.
        // If drawing fails (invalid syntax from the model), the code is
        // shown as it is (class ai-rich-failed), the answer stays readable.
        // Mermaid (~3.5 MB) and Chart.js are only loaded when an answer
        // actually contains such a block.
        async renderRichBlocks(container) {
            if (!container) return;
            const blocks = Array.from(container.querySelectorAll(
                'pre > code.language-mermaid, pre > code.language-chart'
            ));
            for (const code of blocks) {
                const pre = code.parentElement;
                if (!pre || pre.dataset.richDone) continue;
                pre.dataset.richDone = '1';
                const source = code.textContent;
                try {
                    const isDiagram = code.classList.contains('language-mermaid');
                    const figure = isDiagram ? await this.drawMermaid(source) : await this.drawChart(source);
                    pre.replaceWith(figure);
                    this.addRichToolbar(figure, isDiagram ? 'diagram' : 'chart');
                } catch (err) {
                    console.warn('[ChatBot] Could not draw block, showing its source instead:', err);
                    pre.classList.add('ai-rich-failed');
                }
            }

            // Markdown tables get the same toolbar (PNG / enlarge).
            container.querySelectorAll('table').forEach(table => {
                if (table.closest('.ai-rich')) return;
                const wrap = document.createElement('div');
                wrap.className = 'ai-rich ai-rich-table';
                table.parentNode.insertBefore(wrap, table);
                wrap.appendChild(table);
                this.addRichToolbar(wrap, 'table');
            });
        },

        // Small buttons in the corner of a diagram / chart / table:
        // enlarge (full-screen view) and download as PNG.
        addRichToolbar(figure, kind) {
            if (figure.parentElement?.classList.contains('ai-rich-frame')) return;
            // The figure scrolls sideways (wide diagrams). The buttons live in a
            // non-scrolling frame around it, so they stay in the corner while
            // the diagram is scrolled.
            const frame = document.createElement('div');
            frame.className = 'ai-rich-frame';
            figure.parentNode.insertBefore(frame, figure);
            frame.appendChild(figure);
            const bar = document.createElement('div');
            bar.className = 'ai-rich-toolbar';
            const button = (icon, label, onClick) => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'ai-rich-btn';
                b.title = label;
                b.setAttribute('aria-label', label);
                b.innerHTML = `<i class="fa ${icon}" aria-hidden="true"></i>`;
                b.addEventListener('click', (e) => { e.stopPropagation(); onClick(); });
                bar.appendChild(b);
            };
            button('fa-expand', 'Enlarge', () => this.openRichViewer(figure));
            button('fa-download', 'Download as PNG', () => this.downloadRichPng(figure, kind));
            frame.appendChild(bar);
        },

        // Full-screen view of a diagram / chart / table. Click or Esc closes.
        openRichViewer(figure) {
            const overlay = document.createElement('div');
            overlay.className = 'ai-rich-viewer';
            const inner = document.createElement('div');
            inner.className = 'ai-rich-viewer-inner ai-message-content';
            const content = figure.cloneNode(true);
            content.querySelector(':scope > .ai-rich-toolbar')?.remove();
            // A chart is a <canvas>: its drawing is not cloned, use a picture of it.
            const srcCanvas = figure.querySelector('canvas');
            const dstCanvas = content.querySelector('canvas');
            if (srcCanvas && dstCanvas) {
                const img = document.createElement('img');
                img.src = srcCanvas.toDataURL('image/png');
                img.style.maxWidth = '100%';
                dstCanvas.replaceWith(img);
            }
            // Fit the screen, but enlarge a small diagram at most 1.6x
            // (a 2-box diagram should not become screen-filling).
            const bigSvg = content.querySelector('.ai-rich-diagram svg');
            const naturalW = bigSvg ? Number(bigSvg.getAttribute('width')) : 0;
            if (bigSvg && naturalW) bigSvg.style.width = `min(100%, ${Math.round(naturalW * 1.6)}px)`;

            inner.appendChild(content);
            overlay.appendChild(inner);

            // × in the top right corner of the screen (also: click outside, Esc).
            const closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.className = 'ai-rich-viewer-close';
            closeBtn.setAttribute('aria-label', 'Close');
            closeBtn.title = 'Close';
            // An SVG cross is centred geometrically; the "×" glyph sits on the
            // font's baseline and always looks slightly off-centre.
            closeBtn.innerHTML = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16">'
                + '<path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" stroke-width="2" '
                + 'stroke-linecap="round" fill="none"/></svg>';
            overlay.appendChild(closeBtn);

            const close = () => { overlay.remove(); document.removeEventListener('keydown', onKey); };
            const onKey = (e) => { if (e.key === 'Escape') close(); };
            closeBtn.addEventListener('click', close);
            overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
            document.addEventListener('keydown', onKey);
            document.body.appendChild(overlay);
        },

        // PNG of only this diagram / chart / table (html2canvas is bundled).
        async downloadRichPng(figure, kind) {
            const name = { diagram: 'diagram', chart: 'chart', table: 'table' }[kind] || 'figure';
            const save = (dataUrl) => {
                const a = document.createElement('a');
                a.href = dataUrl;
                a.download = `${name}-${new Date().toISOString().slice(0, 10)}.png`;
                document.body.appendChild(a);
                a.click();
                a.remove();
            };
            try {
                const canvas = figure.querySelector('canvas');
                if (kind === 'chart' && canvas) {
                    // Chart.js draws on a transparent canvas: put it on a white/dark background.
                    const out = document.createElement('canvas');
                    out.width = canvas.width;
                    out.height = canvas.height;
                    const ctx = out.getContext('2d');
                    ctx.fillStyle = getComputedStyle(figure).backgroundColor || '#ffffff';
                    if (/rgba\(0, 0, 0, 0\)|transparent/.test(ctx.fillStyle)) ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, out.width, out.height);
                    ctx.drawImage(canvas, 0, 0);
                    save(out.toDataURL('image/png'));
                    return;
                }
                const bg = getComputedStyle(document.body).getPropertyValue('--ai-bg-0').trim() || '#ffffff';

                const svg = figure.querySelector('svg');
                if (kind === 'diagram' && svg) {
                    // The whole diagram, also the part scrolled out of view:
                    // draw the SVG itself onto a canvas (labels are plain SVG
                    // text, see drawMermaid), at 2x for sharpness.
                    const w = Number(svg.getAttribute('width')) || svg.getBoundingClientRect().width;
                    const h = Number(svg.getAttribute('height')) || svg.getBoundingClientRect().height;
                    const xml = new XMLSerializer().serializeToString(svg);
                    const img = new Image();
                    await new Promise((resolve, reject) => {
                        img.onload = resolve;
                        img.onerror = () => reject(new Error('SVG could not be loaded as image'));
                        img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
                    });
                    const pad = 16, scale = 2;
                    const out = document.createElement('canvas');
                    out.width = (w + 2 * pad) * scale;
                    out.height = (h + 2 * pad) * scale;
                    const ctx = out.getContext('2d');
                    ctx.scale(scale, scale);
                    ctx.fillStyle = bg;
                    ctx.fillRect(0, 0, w + 2 * pad, h + 2 * pad);
                    ctx.drawImage(img, pad, pad, w, h);
                    save(out.toDataURL('image/png'));
                    return;
                }

                // Table: only the table itself (not the full-width wrapper).
                await this.loadVendor('html2canvas/html2canvas.min.js');
                const target = figure.querySelector('table') || figure;
                const bar = figure.parentElement?.querySelector(':scope > .ai-rich-toolbar');
                if (bar) bar.style.visibility = 'hidden';
                let shot;
                try {
                    // Tables are display:block (scrollable) in the chat, i.e. as wide
                    // as the bubble: crop to the width of their rows.
                    const rowWidth = Math.max(0, ...Array.from(target.querySelectorAll('tr'))
                        .map(tr => Math.ceil(tr.getBoundingClientRect().width)));
                    shot = await window.html2canvas(target, {
                        backgroundColor: bg, scale: 2,
                        width: Math.max(rowWidth, 1) || target.scrollWidth, height: target.scrollHeight,
                        windowWidth: Math.max(document.documentElement.clientWidth, target.scrollWidth + 40),
                    });
                } finally {
                    if (bar) bar.style.visibility = '';
                }
                save(shot.toDataURL('image/png'));
            } catch (err) {
                console.error('[ChatBot] PNG export failed:', err);
                Notification.alert('Export', 'The image could not be created.', 'OK');
            }
        },

        async drawMermaid(source) {
            await this.loadVendor('mermaid/mermaid.min.js');
            const mermaid = window.mermaid;
            const theme = document.body.dataset.theme === 'dark' ? 'dark' : 'default';
            if (this._mermaidTheme !== theme) {
                // securityLevel strict: no HTML labels / click handlers from model text.
                // htmlLabels false: labels as plain SVG text (no <foreignObject>),
                // so the diagram can be exported as PNG.
                mermaid.initialize({
                    startOnLoad: false, securityLevel: 'strict', theme,
                    htmlLabels: false, flowchart: { htmlLabels: false, useMaxWidth: false },
                });
                this._mermaidTheme = theme;
            }
            // Validate first: a failed render() leaves Mermaid's own error
            // graphic in the page. Models often put ( ) / : etc. into unquoted
            // labels, e.g. A[Vorbereitung (optional)] — then a second try with
            // every [label] / {label} quoted.
            const valid = async (text) => (await mermaid.parse(text, { suppressErrors: true })) !== false;
            let text = source;
            if (!(await valid(text))) {
                const fixed = this.quoteMermaidLabels(source);
                if (fixed === source || !(await valid(fixed))) throw new Error('invalid Mermaid diagram');
                text = fixed;
            }
            const id = 'ai-mermaid-' + Date.now() + '-' + Math.floor(Math.random() * 1e6);
            let svg;
            try {
                ({ svg } = await mermaid.render(id, text));
            } finally {
                // Mermaid's temporary render container, should it be left behind.
                document.getElementById('d' + id)?.remove();
            }
            const figure = document.createElement('div');
            figure.className = 'ai-rich ai-rich-diagram';
            figure.innerHTML = svg;
            // Natural size, never squeezed to the bubble width (a 6-step
            // flow became unreadably small). Too wide -> horizontal scroll.
            const svgEl = figure.querySelector('svg');
            const vb = svgEl && svgEl.viewBox && svgEl.viewBox.baseVal;
            if (svgEl && vb && vb.width) {
                svgEl.style.maxWidth = 'none';
                svgEl.setAttribute('width', Math.round(vb.width));
                svgEl.setAttribute('height', Math.round(vb.height));
            }
            return figure;
        },

        // A[text] -> A["text"], B{text} -> B{"text"}; already quoted labels stay.
        quoteMermaidLabels(source) {
            const quote = (text) => '"' + text.replace(/"/g, '#quot;') + '"';
            return source
                .replace(/(\b[\w-]+)\[(?!["\[(\/\\])([^\]\n]+)\]/g, (m, id, text) => `${id}[${quote(text)}]`)
                .replace(/(\b[\w-]+)\{(?![{"])([^}\n]+)\}/g, (m, id, text) => `${id}{${quote(text)}}`);
        },

        async drawChart(source) {
            const spec = JSON.parse(source);
            const allowed = ['bar', 'line', 'pie', 'doughnut'];
            const type = allowed.includes(spec.type) ? spec.type : 'bar';
            if (!Array.isArray(spec.labels) || !Array.isArray(spec.datasets) || !spec.datasets.length) {
                throw new Error('chart block needs "labels" and "datasets"');
            }
            await this.loadVendor('chartjs/chart.umd.min.js');

            const figure = document.createElement('div');
            figure.className = 'ai-rich ai-rich-chart';
            const canvas = document.createElement('canvas');
            figure.appendChild(canvas);

            const dark = document.body.dataset.theme === 'dark';
            const textColor = dark ? '#e8e6e1' : '#2b2a27';
            const gridColor = dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.08)';

            // Created after the figure is in the page (Chart.js needs a size).
            requestAnimationFrame(() => {
                new window.Chart(canvas, {
                    type,
                    data: {
                        labels: spec.labels.map(String),
                        datasets: spec.datasets.map(d => ({
                            label: String(d.label || ''),
                            data: (d.data || []).map(Number),
                        })),
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        animation: false,
                        plugins: {
                            title: { display: !!spec.title, text: String(spec.title || ''), color: textColor },
                            legend: { labels: { color: textColor } },
                        },
                        scales: (type === 'pie' || type === 'doughnut') ? {} : {
                            x: { ticks: { color: textColor }, grid: { color: gridColor },
                                 title: { display: !!spec.x_label, text: String(spec.x_label || ''), color: textColor } },
                            y: { ticks: { color: textColor }, grid: { color: gridColor }, beginAtZero: true,
                                 title: { display: !!spec.y_label, text: String(spec.y_label || ''), color: textColor } },
                        },
                    },
                });
            });
            return figure;
        },

        // =========================
        // MARKDOWN + MATH → HTML (every message goes through here)
        // =========================
        // The markdown parser eats the backslashes of LaTeX ("\(" becomes
        // "(", "\varepsilon" breaks), so formulas are taken OUT before
        // parsing and replaced by placeholders, and rendered with KaTeX
        // afterwards. Recognised: $$...$$ and \[...\] (display),
        // \(...\) and $...$ (inline; "$5 and $10" is NOT math because a
        // closing $ must not follow a space). Code (```...``` and `...`)
        // is left untouched. An unfinished formula during streaming simply
        // stays as text until its closing delimiter arrives.
        renderMarkdown(text) {
            text = text || '';
            const marked = window.marked;
            const katex = window.katex;
            if (!marked) return text;
            if (!katex) return marked.parse(text);

            const formulas = [];
            const stash = (tex, display) => {
                formulas.push({ tex, display });
                return `KATEXMATH${formulas.length - 1}X`;
            };
            const extract = (part) => part
                .replace(/\$\$([\s\S]+?)\$\$/g, (m, tex) => stash(tex, true))
                .replace(/\\\[([\s\S]+?)\\\]/g, (m, tex) => stash(tex, true))
                .replace(/\\\(([\s\S]+?)\\\)/g, (m, tex) => stash(tex, false))
                .replace(/(^|[^\\$\w])\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)/g,
                    (m, pre, tex) => pre + stash(tex, false));

            // Split off code blocks / inline code, extract math only from the rest.
            const pieces = text.split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g);
            const prepared = pieces.map((piece, i) => (i % 2 === 1 ? piece : extract(piece))).join('');

            let html = marked.parse(prepared);
            if (!formulas.length) return html;

            return html.replace(/KATEXMATH(\d+)X/g, (m, idx) => {
                const f = formulas[Number(idx)];
                if (!f) return m;
                try {
                    return katex.renderToString(f.tex.trim(), {
                        displayMode: f.display, throwOnError: false, output: 'html'
                    });
                } catch (err) {
                    return f.display ? `$$${f.tex}$$` : `$${f.tex}$`;
                }
            });
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
                if (e && e.handled) {
                    // Refused before anything was saved: take the message back out of the
                    // conversation and into the input box (with its image), so it can be sent again.
                    userWrap.remove();
                    const input = document.getElementById('ai-message-input');
                    if (input && !input.value) {
                        input.value = message;
                        input.dispatchEvent(new Event('input'));
                    }
                    if (pendingImage && !this.state.pendingImage) {
                        this.setPendingImage(pendingImage.file);
                    }
                }
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
            if (!response.ok) {
                // The backend (via stream.php) refused the request: show why, instead of an empty bubble.
                const text = await this.describeStreamError(response);
                bubbleTextEl.innerHTML = '';
                const note = document.createElement('div');
                note.className = 'ai-stream-error';
                note.style.color = 'var(--bs-danger, #b42318)';
                note.textContent = text;
                bubbleTextEl.appendChild(note);

                const err = new Error('stream_http_' + response.status);
                err.handled = true;
                err.status = response.status;
                throw err;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let fullText = '';

            // Smooth typing: some providers (KI:connect) send the answer in
            // big bursts instead of token by token. Received text goes into
            // fullText; a frame loop reveals it a few characters per frame,
            // faster the more is waiting, so it never falls behind for long.
            let shownLen = 0;
            let frame = null;
            const renderText = (text) => {
                try {
                    bubbleTextEl.innerHTML = this.renderMarkdown(text);
                } catch (err) {
                    bubbleTextEl.innerText = text;
                }
            };
            const tick = () => {
                frame = null;
                const backlog = fullText.length - shownLen;
                if (backlog <= 0) return;
                // Background tab: no animation, just show everything.
                shownLen = document.hidden
                    ? fullText.length
                    : shownLen + Math.max(2, Math.ceil(backlog / 12));
                renderText(fullText.slice(0, shownLen));
                this.scrollToBottom();
                frame = requestAnimationFrame(tick);
            };
            const kick = () => { if (frame === null) frame = requestAnimationFrame(tick); };
            const waitUntilShown = () => new Promise(resolve => {
                const started = Date.now();
                const check = () => {
                    if (shownLen >= fullText.length || document.hidden || Date.now() - started > 4000) {
                        resolve();
                    } else {
                        setTimeout(check, 30);
                    }
                };
                check();
            });

            try {
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
                        // The AI service did not answer (e.g. Mistral rate limit even
                        // after the backend's retries): say so instead of an empty bubble.
                        if (parsed.error === 'llm_unavailable' && !fullText) {
                            bubbleTextEl.innerText =
                                'The AI service is busy right now. Please send your question again in a moment.';
                        }
                        continue;
                    }

                    const token = parsed.token;
                    fullText += token;
                    this.state.partialText = fullText;
                    kick();
                }
            }

            // Let the typing animation finish before the final render.
            await waitUntilShown();
            } finally {
                if (frame !== null) cancelAnimationFrame(frame);
                frame = null;
            }

            try {
                bubbleTextEl.innerHTML = this.renderMarkdown(fullText);
            } catch (err) {
                bubbleTextEl.innerText = fullText;
            }

            this.renderSourceCards(bubbleTextEl);
            this.renderRichBlocks(bubbleTextEl);

            const wrap = bubbleTextEl.closest('.ai-message');
            if (wrap) wrap.dataset.rawContent = fullText;

            return fullText;
        },

        // Human-readable text for an error answer of the stream endpoints.
        async describeStreamError(response) {
            let detail = '';
            try {
                const data = JSON.parse(await response.text());
                detail = String(data.detail || data.error || '');
            } catch (e) {
                // body is not JSON, the status code alone has to do
            }

            switch (response.status) {
                case 429: {
                    const wait = parseInt(response.headers.get('Retry-After'), 10);
                    return 'You are sending messages too quickly. Please wait '
                        + (wait > 0 ? wait + ' seconds' : 'a moment') + ' and try again.';
                }
                case 403:
                    return /enrolled/i.test(detail)
                        ? 'You are not enrolled in this course, so you cannot chat about it.'
                        : 'You do not have access to this chat.';
                case 401:
                    return 'The chatbot could not verify your session. Please reload the page and try again.';
                case 413:
                    return 'The message or the image is too large.';
                default:
                    return 'Something went wrong while generating the answer. Please try again.';
            }
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
            contentEl.innerHTML = this.renderMarkdown(newContent);
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

            await this.loadThread(sessionId);
        },

        // =========================
        // LOAD + RENDER THE ACTIVE THREAD (progressive translation)
        // =========================
        // Asks for the thread with cached_only: the backend answers at once —
        // cached translations where they exist, the original text (marked
        // translation_pending) where not. A chat shown in its original
        // language, or one that is already fully translated, therefore
        // appears complete immediately. Pending messages are rendered dimmed
        // and replaced one by one as their translations arrive.
        async loadThread(sessionId, { versionNav = true } = {}) {
            const result = await Ajax.call([{
                methodname: 'local_ai_system_get_messages',
                args: { session_id: sessionId, cached_only: true }
            }])[0];

            const messages = Array.isArray(result) ? result : (result.messages ?? []);

            const run = ++this.state.translationRun;
            const container = document.getElementById('ai-messages-container');
            container.innerHTML = '';

            const pending = [];
            messages.forEach(msg => {
                const wrap = this.appendMessage(msg.role, msg.content, msg.created_at, msg.image_url, msg.id);
                if (msg.translation_pending && msg.id) {
                    wrap.classList.add('ai-message--translating');
                    pending.push({ id: msg.id, role: msg.role, wrap });
                }
            });

            if (versionNav) await this.loadVersionNav();

            // Not awaited: the chat is usable while translations stream in.
            if (pending.length) this.translatePending(sessionId, pending, run);

            return messages;
        },

        async translatePending(sessionId, pending, run) {
            const PARALLEL = 4; // browser -> Moodle requests at once; the backend parallelises further

            // Every render bumps translationRun (opening another chat, switching
            // language, editing...), so this alone drops results meant for a
            // chat that is no longer on screen. Not compared with state.sessionId
            // on purpose: archived chats render with sessionId = null.
            const stale = () => run !== this.state.translationRun;

            // Translations are FETCHED in parallel (fast), but SHOWN strictly
            // top to bottom: message 1, then 2, then 3 ... A finished
            // translation waits in `done` until every message above it has
            // been shown, so the chat never fills in a random order.
            const done = new Map();   // index -> translated text (null = failed, keep original)
            let shown = 0;            // index of the next message to show
            const flush = () => {
                while (shown < pending.length && done.has(shown)) {
                    const item = pending[shown];
                    const content = done.get(shown);
                    if (content !== null) this.setMessageContent(item.wrap, item.role, content);
                    item.wrap.classList.remove('ai-message--translating');
                    shown++;
                }
            };

            let next = 0;             // index of the next message to fetch
            const worker = async () => {
                while (next < pending.length && !stale()) {
                    const index = next++;
                    const item = pending[index];
                    let content = null;
                    try {
                        const res = await Ajax.call([{
                            methodname: 'local_ai_system_translate_message',
                            args: { session_id: sessionId, message_id: item.id }
                        }])[0];
                        content = res.content;
                    } catch (e) {
                        // Leave the original text; the next open retries (nothing was cached).
                        console.error('[ChatBot] Translation failed for message', item.id, e);
                    }
                    if (stale()) return;
                    done.set(index, content);
                    flush();
                }
            };

            await Promise.all(Array.from({ length: Math.min(PARALLEL, pending.length) }, worker));
        },

        // Replaces the text of a rendered message (keeps image, time, actions).
        setMessageContent(wrap, role, content) {
            const text = wrap.querySelector('.ai-message-content');
            if (!text) return;
            wrap.dataset.rawContent = content || '';
            text.innerHTML = this.renderMarkdown(content);
            if (role === 'assistant') {
                this.renderSourceCards(text);
                this.renderRichBlocks(text);
            }
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
            text.innerHTML = this.renderMarkdown(content);
            if (role === 'assistant') {
                this.renderSourceCards(text);
                this.renderRichBlocks(text);
            }

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

            btn.addEventListener('click', () => {
                this.closeArchivePanel();
                this.startDraftChat();
            });
        },

        // "New Chat" only switches to the empty start screen. The chat itself is
        // created on the backend by ensureSession() when the first message is
        // sent, so clicking the button without writing anything leaves no empty
        // chat behind in the sidebar and the database.
        startDraftChat() {
            this.state.sessionId = null;

            document.querySelectorAll('.ai-session-item').forEach(e => e.classList.remove('active'));
            document.getElementById('ai-messages-container').innerHTML = '';
            document.getElementById('ai-chat-title').textContent = 'SDG-Campus AI Chatbot';

            // An archived chat disables the input; a new chat must be writable again.
            const input = document.getElementById('ai-message-input');
            const sendBtn = document.getElementById('ai-send-btn');
            if (input) { input.disabled = false; input.placeholder = 'Type your message...'; }
            if (sendBtn) sendBtn.disabled = false;

            this.clearPendingImage();
            this.setActiveLanguage('');
            this.setCourseLock(false);
        },
    };

    return {
        init: (sessionId, courseId) => ChatBot.init(sessionId, courseId)
    };
});
