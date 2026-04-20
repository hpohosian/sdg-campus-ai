# 🎨 Frontend Architecture — SDG Campus AI (Moodle Plugin)

## 📌 Overview

The frontend layer of the SDG Campus AI system is responsible for:

- rendering the chatbot UI inside Moodle
- handling user interactions
- sending requests to backend via Moodle AJAX
- displaying AI responses in real-time

The frontend is implemented using:

- **Moodle Mustache templates*- (UI structure)
- **AMD JavaScript modules*- (logic & behavior)

---

## 🧩 Architecture Overview

```text
Mustache Template (HTML UI)
↓
AMD JavaScript Module (chatbot.js)
↓
Moodle AJAX (core/ajax)
↓
Moodle PHP API (external function)
↓
Backend (FastAPI + LLM)
```

---

## 🧱 UI Layer — Mustache Template

📌 File: `templates/chatbot.mustache`

---

## 🎯 Purpose

Defines the **static structure of the chatbot UI*- rendered inside Moodle.

---

## 🧩 Main Components

### 1. Container

```html
<div id="ai-chatbot" class="ai-chatbot-container">
```

- root element of chatbot UI
- holds entire component

---

### 2. Header

- chatbot title (localized)
- "new session" button (UI placeholder)

---

### 3. Messages Area

```html
<div id="ai-messages-container">
```

- displays chat history
- populated from backend (`messages`)

---

### 4. Message Rendering

```html
<div class="ai-message ai-message--{{role}}">
```

- role-based styling (`user`, `assistant`)
- supports HTML rendering (`{{{content_html}}}`)

---

### 5. Input Area

- textarea input
- send button
- typing indicator

---

## 🔄 Template Data Flow

```text
PHP (index.php)
    ↓
session_id + messages
    ↓
Mustache template
    ↓
Rendered HTML
```

---

## ⚙️ Logic Layer — chatbot.js

📌 File: `amd/src/chatbot.js`

---

## 🧠 Module Type

Moodle AMD module:

```js
define(['core/ajax', 'core/str', 'core/notification'], function(...)
```

---

## 📦 Dependencies

- `core/ajax` → backend communication
- `core/notification` → error handling
- `core/str` → localization (reserved for future use)

---

## 🧠 Internal State

```js
sessionId
isLoading
```

---

## 🔄 Lifecycle

### 1. Initialization

```js
init(sessionId)
```

- receives session ID from PHP
- binds events
- scrolls chat to bottom

---

### 2. Event Binding

```js id="bind_events"
click → sendMessage()
Enter → sendMessage()
```

- Enter (without Shift) sends message
- Shift+Enter allows multiline input

---

## 📤 Sending Message

### Step 1 — Validate input

```js id="input_validation"
if (!message) return;
```

---

### Step 2 — Update UI immediately

```js id="optimistic_ui"
appendMessage('user', message)
```

- user message appears instantly
- improves UX responsiveness

---

### Step 3 — Send AJAX request

```js id="ajax_request"
Ajax.call([{
    methodname: 'local_ai_system_send_message',
    args: { session_id, message }
}])
```

---

### Step 4 — Handle response

```js id="handle_response"
const response = result.message;
const newSessionId = result.session_id;
```

- updates session if changed
- appends assistant response

---

### Step 5 — Error handling

```js id="error_handling"
Notification.exception(err)
```

---

### Step 6 — Reset loading state

```js id="loading_state"
setLoading(false)
```

---

## 💬 Message Rendering

### appendMessage()

```js id="append_message"
appendMessage(role, content, isMarkdown)
```

---

### Behavior

- creates DOM element
- assigns role-based class
- appends to container
- auto-scrolls

---

### Markdown Support (planned)

```js id="markdown"
renderMarkdown(text)
```

- currently returns raw text
- placeholder for future markdown parsing

---

## ⏳ Loading State

```js id="loading"
setLoading(state)
```

---

### Effects

- disables send button
- shows typing indicator
- prevents duplicate requests

---

## 🔽 Auto Scroll

```js id="scroll"
scrollToBottom()
```

- keeps latest messages visible
- called after each update

---

## 🔄 Full Frontend Flow

```id="frontend_flow"
User types message
    ↓
chatbot.js captures event
    ↓
UI updates (user message)
    ↓
AJAX request (Moodle)
    ↓
Response received
    ↓
UI updates (AI message)
```

---

## 🧠 Design Principles

### 1. Moodle-native frontend

- uses AMD modules (not ES modules)
- uses Mustache templates
- integrates with Moodle core APIs

---

### 2. Optimistic UI updates

- user message appears instantly
- improves perceived performance

---

### 3. Stateless frontend

- relies on `sessionId`
- no complex client-side memory

---

### 4. Minimal state management

- only `sessionId` and `isLoading`
- avoids unnecessary complexity

---

### 5. Progressive enhancement

- markdown support planned
- streaming support planned

---

## 🚧 Current Limitations

- no markdown rendering (placeholder only)
- no streaming responses
- no message editing/regeneration
- no error UI (only exception popup)
- no client-side caching

---

## 🚀 Future Improvements

### 🌊 Streaming responses

- display tokens as they arrive
- typing effect

---

### 🎨 Rich content support

- markdown parsing
- syntax highlighting
- code blocks

---

### 🧠 UX improvements

- message actions (copy, retry)
- better loading states
- animations

---

### 📱 Responsive UI

- mobile optimization
- adaptive layout

---

### 🔄 Session control

- "new session" button functionality
- session switching

---

## 🎯 Summary

The frontend layer is a **lightweight, Moodle-integrated UI system*- that:

- renders chatbot interface via Mustache
- handles interactions via AMD JavaScript
- communicates with backend through Moodle AJAX
- provides responsive and simple chat experience

It is intentionally minimal and modular, serving as a foundation for more advanced UI features in future iterations.
