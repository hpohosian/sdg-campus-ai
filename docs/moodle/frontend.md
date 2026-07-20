# Moodle Plugin — Frontend (UI)

The chat widget's UI is built from three files working together: a server-rendered
Mustache template (initial HTML/state), a CSS file (all visual styling), and an AMD
JavaScript module (all interactivity after page load).

## Template (`templates/chatbot.mustache`)

Server-rendered by `index.php`. Responsible for:

- **Sidebar**: course picker (only rendered if the user has enrolled courses —
  `{{#has_courses}}`), "New Chat" button, three session groups (`Pinned` — always starts
  empty since pins aren't persisted server-side; `Today`; `Previous` — hidden until the
  JS moves stale items into it), and the archive dropdown (populated server-side from
  `archived_sessions`, or an "empty" message if none exist).
- **Header**: chat title, pin button, export/share buttons (both disabled,
  `coming_soon`), theme toggle, and the language picker dropdown (hard-coded to English,
  German, Russian, Ukrainian — `en`/`de`/`ru`/`uk`).
- **Message list**: pre-renders any existing messages passed in via `{{#messages}}` —
  though in practice `index.php` currently always passes an empty `history.messages`
  array (see note in [moodle/overview.md](overview.md) / `index.php`'s `$history =
  ['messages' => []]`), so this block is effectively unused at initial page load; message
  loading actually happens client-side via `loadSession()`/AJAX after `init()` runs, not
  from server-rendered content. The template block is still valid/functional if that
  variable were ever populated in the future.
- **Input area**: message textarea, send/stop buttons, and a disabled attach-file button
  (`coming_soon`).
- **Two floating, single-instance elements mounted once**: the session context menu
  (`#ai-context-menu` — pin/rename/archive/delete) and the rename popup
  (`#ai-rename-popup`). Both get reparented to `<body>` at JS init time (see below) to
  avoid clipping issues from ancestor `overflow`/`transform` CSS.

All user-facing strings go through `{{#str}} key, local_ai_system {{/str}}` — pulling from
`lang/en/local_ai_system.php`, so adding another language is a matter of adding a new
`lang/xx/local_ai_system.php` file with the same keys.

## Styling (`styles.css`, 667 lines)

Class naming convention is consistently prefixed `ai-*`
(`ai-chatbot-layout`, `ai-session-item`, `ai-message-bubble`, etc.) to avoid clashing with
Moodle theme classes. Key structural pieces styled:

- `.ai-chatbot-layout` — the two-column (sidebar + main) flex layout.
- `.ai-session-item` / `.ai-session-archived` / `.active` — sidebar chat list rows.
- `.ai-message`, `.ai-message--user` / `.ai-message--assistant`, `.ai-bubble-wrap`,
  `.ai-message-bubble` — chat bubble styling, differentiated by role.
- `.ai-course-picker`, `.ai-language-picker` — the two dropdown pickers, sharing a
  similar toggle/dropdown/option visual pattern.
- `.ai-context-menu`, `.ai-popup` — the floating menu/rename dialogs.
- `.ai-translating-overlay` — the spinner shown over the message list during a language
  switch.
- **Dark theme**: applied via `[data-theme="dark"]` attribute selectors scoped from
  `document.body.dataset.theme` (set/cleared by `chatbot.js`'s theme toggle) — not a
  separate stylesheet, the same file carries both light and dark rules.

## JavaScript module (`amd/src/chatbot.js`, 998 lines)

A single object literal, `ChatBot`, exposing only an `init(sessionId, courseId)` entry
point via the AMD module's returned interface — everything else is a "private" method on
the same object (JS doesn't enforce privacy here; it's a convention). Compiled to
`amd/build/chatbot.min.js`, which is what Moodle actually loads in production (AMD
modules are built via Moodle's grunt/webpack tooling from `amd/src/`, not from source
directly) — **remember to rebuild `amd/build/chatbot.min.js` after editing
`amd/src/chatbot.js`**, or changes won't take effect in the browser.

### `init()` responsibilities

- Reparents the context menu and rename popup to `<body>`.
- Wires up: markdown rendering config, theme, all click/keyboard handlers, session
  grouping by date, new-session button, language picker, header pin button, archive
  toggle, course picker, message timestamp formatting.
- Restores the active session's language indicator.
- Sets the initial course-lock state based on whether the currently active session
  already has messages.
- Binds scroll tracking (`shouldAutoScroll`) and link-click interception (opens links in
  a new tab, `target="_blank" rel="noopener noreferrer"` equivalent via `window.open`) on
  the message container.

### State (`ChatBot.state`)

```js
{
  sessionId, courseId, isStreaming, isTranslating,
  controller,       // AbortController for the in-flight stream, if any
  shouldAutoScroll, // whether new tokens should auto-scroll the view
  partialText,      // accumulated text of an in-progress stream (for Stop → save-partial)
  pinned: {}        // { [sessionId]: true } — CLIENT-SIDE ONLY, not persisted (see below)
}
```

### Notable behaviors

- **Pinning is not persisted.** `togglePin`/`state.pinned` only exists in memory for the
  current page load — reloading the page (or reopening the chat panel, since the iframe
  is destroyed/recreated) resets all pins. There is no backend endpoint or DB column for
  pin state at all. If persistent pinning is wanted, it needs a new session column/API
  endpoint on the Python side plus wiring here.
- **Streaming** (`sendMessageStream`): appends the user bubble optimistically, creates an
  empty assistant bubble, ensures a session exists (creating one on first send if
  needed), locks the course picker, then `fetch()`s `ajax/stream.php` with the
  `AbortController` signal. Reads the response body as a stream, splits on newlines,
  parses `data: ...` SSE lines as JSON — a `{"title": ...}` payload updates the header
  and sidebar title, a `{"token": ...}` payload appends to the running text and
  re-renders the bubble via `marked.parse()` on every single token (not batched/
  throttled — for very fast/long streams this means a full markdown re-parse per token,
  which is simple but not the most efficient approach if performance ever becomes an
  issue on long responses).
- **Stop button**: aborts the fetch, then POSTs whatever partial text had accumulated to
  `local_ai_system_save_partial_message` so it isn't lost (see
  [data-flow.md](../../data-flow.md#stopping-generation-mid-stream)).
- **Course lock**: the course picker is disabled once the *active chat* has at least one
  message — not merely because a session row exists (a freshly created empty chat can
  still have its course changed). Locking happens explicitly at send-time
  (`setCourseLock(true)` inside `sendMessageStream`), not at session-creation time.
- **Session loading** (`loadSession`) is the single source of truth for populating the
  message list, used both when clicking a sidebar item and (indirectly) after a language
  switch. Archived sessions load in a read-only state (input disabled, "Unarchive to send
  messages" placeholder).
- **Global click delegation** (`bindGlobalDelegation`): a single document-level click
  listener handles clicks on session items, session menu buttons, and clicks-outside-to-
  close-menu, rather than binding a listener per sidebar item — this is what lets
  dynamically-created session items (from `addSessionToSidebar`/`addSessionToArchive`,
  used when creating/archiving sessions without a full page reload) work without any
  extra re-binding step.
- **Message action buttons** (copy/regenerate/edit/thumbs-up/down) are rendered for every
  message (`messageActionsHtml`), and **copy** is the only one actually wired up
  (`navigator.clipboard.writeText`, with a brief checkmark-icon confirmation). Regenerate
  and edit currently just `console.log` a "not implemented yet" message; thumbs up/down
  only toggle a local `.active` CSS class with no backend call at all — no feedback data
  is sent or stored anywhere yet. There is no feedback or analytics module anywhere in
  the codebase yet (no PHP classes, no DB tables, no JS) — this is planned, per the
  top-level README, but nothing has been scaffolded for it.
- **Markdown rendering**: relies on the global `marked` library, loaded via CDN
  (`https://cdn.jsdelivr.net/npm/marked/marked.min.js`) in `index.php`, configured with
  `{ breaks: true, gfm: true }`. There is no fallback/self-hosted copy — if the CDN is
  unreachable (e.g. restricted network), markdown rendering silently degrades to raw text
  via the `try/catch` around `marked.parse()` calls scattered through the file, but the
  initial `M.cfg` script include itself would simply fail to load with no explicit error
  handling for that case.

## Planned modules not yet present

The top-level README lists feedback collection and analytics as planned features. As of
this codebase, there is no `classes/feedback/`, `classes/analytics/`,
`amd/src/feedback.js`, or `amd/src/analytics.js` anywhere in the plugin — only the
`amd/src/chatbot.js` module (and its compiled `amd/build/chatbot.min.js`) exists today.
The thumbs up/down buttons in the chat UI are purely cosmetic placeholders for this
future work (see above).
