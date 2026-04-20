# 🎓 Moodle Plugin Integration — SDG Campus AI

## 📌 Overview

This document describes the **Moodle plugin layer** of the SDG Campus AI system.

The plugin acts as a **bridge between Moodle (PHP frontend)** and the **Python AI backend (FastAPI)**.

It is responsible for:

- rendering the chatbot UI inside Moodle
- handling user authentication and permissions
- managing frontend interactions (JavaScript)
- communicating with AI backend via API
- integrating AI responses into Moodle UI

---

## 🧩 Plugin Structure

```text
moodle-plugin/local/ai_system/
├── index.php
├── amd/src/chatbot.js
├── templates/chatbot.mustache
├── classes/external/
│   ├── api_client.php
│   └── chatbot_api.php
```

---

## 🚪 Entry Point — index.php

📌 File: `index.php`

---

### Purpose

This file is the **main entry point** for the AI chatbot page inside Moodle.

---

### Responsibilities

- checks user authentication
- validates permissions
- initializes session
- loads chat history
- renders UI template
- injects JavaScript frontend

---

### Flow

```text
require_login()
    ↓
check capability (use_chatbot)
    ↓
create session_id
    ↓
load chat history
    ↓
render mustache template
    ↓
initialize AMD JS module
```

---

### Session Handling

```php
$session_id = optional_param('session_id', null, PARAM_TEXT);

if (!$session_id) {
    $session_id = uniqid('chat_', true);
}
```

- each chat session has unique ID
- allows conversation persistence
- connects frontend ↔ backend ↔ DB

---

### Template Rendering

```php
echo $OUTPUT->render_from_template(
    'local_ai_system/chatbot',
    $templatecontext
);
```

- passes session_id + messages
- renders Mustache UI

---

### JS Initialization

```php
$PAGE->requires->js_call_amd(
    'local_ai_system/chatbot',
    'init',
    [$session_id]
);
```

- loads frontend logic
- connects UI to backend API

---

## 🎨 Frontend Layer — chatbot.js

📌 File: `amd/src/chatbot.js`

---

## 🧠 Purpose

This module handles **all frontend chatbot interactions inside Moodle UI**.

---

## 🔄 Core Responsibilities

### 1. UI Event Handling

- send button click
- Enter key press

---

### 2. Message Sending

Uses Moodle AJAX system:

```js
Ajax.call([{
    methodname: 'local_ai_system_send_message',
    args: {
        session_id: this.sessionId,
        message: message,
    }
}])
```

---

### 3. UI Updates

- append user messages
- append assistant responses
- scroll chat
- show typing indicator

---

### 4. State Management

```js
sessionId
isLoading
```

- prevents duplicate requests
- maintains session continuity

---

## 🧾 Template Layer — chatbot.mustache

📌 File: `templates/chatbot.mustache`

---

## 🎨 Purpose

Defines the **UI structure of the chatbot inside Moodle**.

---

## 🧩 Components

### 1. Header

- title
- new session button

---

### 2. Messages container

```html
<div id="ai-messages-container">
```

- renders chat history
- loops through messages

---

### 3. Input area

- textarea input
- send button
- typing indicator

---

## 🔄 Data Flow into Template

```text
PHP index.php
    ↓
$history + session_id
    ↓
Mustache template
    ↓
Rendered HTML in Moodle page
```

---

## 🔌 Backend Integration Layer

---

## 📡 api_client.php

📌 File: `classes/external/api_client.php`

---

### Purpose

This class is responsible for **communication between Moodle and FastAPI backend**.

---

## 🔄 Responsibilities

### 1. HTTP communication

- sends POST requests to backend
- uses curl internally

---

### 2. Security layer

Each request includes:

```text
X-Timestamp: ...
X-Signature: HMAC_SHA256(...)
```

---

### 3. Request flow

```text
Moodle PHP
    ↓
api_client.php
    ↓
FastAPI backend
    ↓
AI response
    ↓
return to Moodle
```

---

## 🧠 chatbot_api.php

📌 File: `classes/external/chatbot_api.php`

---

## Purpose

This is Moodle’s **external web service layer**.

It exposes chatbot functionality as **Moodle web services API**.

---

## 📍 Endpoints

### 1. send_message()

Handles sending messages from Moodle to backend.

Flow:

```text
validate input
check permissions
call service
return response
```

---

### 2. get_history()

Returns chat history for session.

---

## 🔐 Security Model

- requires login (`require_login()`)
- checks capability:

  ```text
  local/ai_system:use_chatbot
  ```

- validates Moodle context

---

## 🧩 Full System Flow (Moodle side)

```text
User
 ↓
index.php
 ↓
Mustache UI
 ↓
chatbot.js (AMD)
 ↓
Moodle AJAX (external function)
 ↓
chatbot_api.php
 ↓
ChatService (Python backend via API client)
 ↓
FastAPI + LLM
 ↓
Response returns back up chain
```

---

## 🧠 Design Principles

### 1. Moodle-native integration

- uses Mustache templates
- uses AMD JS modules
- follows Moodle plugin standards

---

### 2. Separation of concerns

- PHP = backend bridge
- JS = UI logic
- Python = AI logic

---

### 3. Secure communication

- capability-based access control
- signed backend requests
- authenticated Moodle session

---

### 4. Extensible architecture

Plugin is designed to support:

- multiple AI modules (chat, analytics, translation)
- future real-time streaming
- course-based RAG integration

---

## 🚧 Current Limitations

- no real-time streaming in UI
- session stored only via ID (no advanced persistence here)
- no frontend caching layer
- AJAX dependency on Moodle web services only

---

## 🚀 Future Improvements

### 🌊 Streaming UI

- live token rendering
- typing simulation improvements

---

### 🧠 Smart UI enhancements

- markdown rendering
- code highlighting
- message actions (copy, regenerate)

---

### 📊 Analytics integration

- track user interaction inside Moodle
- learning behavior analysis

---

### 🔗 RAG integration

- show course-based AI answers
- context-aware responses per course

---

## 🎯 Summary

The Moodle plugin is the **frontend integration layer of the SDG Campus AI system**.

It:

- embeds AI into Moodle UI
- connects frontend to Python backend
- handles user interaction
- ensures secure communication
- follows Moodle plugin architecture standards

It acts as the **bridge between educational platform and AI system**, enabling seamless AI-powered learning inside Moodle.
