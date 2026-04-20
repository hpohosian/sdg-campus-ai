# 🔄 Data Flow — SDG Campus AI Chat System

## 📌 Overview

This document describes how data flows through the SDG Campus AI Chat system, from user input in Moodle to AI-generated responses and back to the UI.

The system consists of three main layers:

- Moodle Plugin (PHP + JavaScript)
- Backend API (FastAPI / Python)
- LLM Layer (Mistral)

---

## 🧩 High-Level Flow

```text
    User (Moodle UI)
            ↓
JavaScript (AMD chatbot.js)
            ↓
Moodle AJAX API (chatbot_api.php)
            ↓
PHP Service Layer (service.php)
            ↓
FastAPI Backend (/chat endpoint)
            ↓
C  hat Service (service.py)
            ↓
     LLM (Mistral)
            ↓
Response returned back through same chain
            ↓
Moodle UI updates message list
```

---

## 💬 Step-by-Step Data Flow

### 1. User Input (Frontend)

- User types a message in Moodle chat UI
- `chatbot.js` captures input from DOM
- Message is validated (non-empty check)

📌 File:

- `amd/src/chatbot.js`

---

### 2. AJAX Request from Moodle

The frontend sends a request via Moodle AJAX API:

```javascript
Ajax.call([{
    methodname: 'local_ai_system_send_message',
    args: {
        session_id: this.sessionId,
        message: message
    }
}])
```

---

### 3. Moodle External API Layer

The request is handled by:
📌 File:

- `chatbot_api.php`

Steps:

1. Validates parameters (session_id, message)
2. Checks user permissions
3. Loads current user ($USER)
4. Calls backend service layer

---

### 4. PHP Service Layer

📌 File:

- `service.php` (implied usage in your architecture)

Responsibilities:

1. Prepares request for backend API
2. Calls Python FastAPI using api_client.php
3. Sends structured payload:
   - user_id
   - session_id
   - message

---

### 5. HTTP Communication (Moodle → FastAPI)

📌 File:

- `api_client.php`

Process:

1. Builds JSON request body
2. Adds security headers:
   - X-Timestamp
   - X-Signature (HMAC SHA256)
3. Sends HTTP POST request to: `http://127.0.0.1:8001/chat`

---

### 6. FastAPI Router Layer

📌 File:

- `router.py`

Endpoint:

- POST /chat

Flow:

1. Receives ChatRequest
2. Injects ChatService via dependency injection
3. Calls: `service.handle_message(request)`

---

### 7. Chat Service Processing

📌 File:

- `service.py`
This is the core logic of the system.

## Step 1: Session handling

- Load or create session: `session_repo.get_or_create(session_id, user_id)`

## Step 2: Load history

- Fetch previous messages: `session_repo.get_messages(session.id)`

## Step 3: Build LLM context

- Combine:
  - system prompt
  - chat history
  - new user message
- Result:

```json
messages = [
  {"role": "system", ...},
  {"role": "user", "content": "history..."},
  {"role": "user", "content": "new message"}
]
```

## Step 4: Call LLM

- Send messages to: `MistralLLM.chat(messages)`

## Step 5: Save messages

- Save user message
- Save assistant response

## Step 6: Return response

```json
{
  "session_id": "...",
  "message": "AI response"
}
```

---

### 8. LLM Layer (Mistral)

📌 File:

- `mistral.py`

Responsibilities:

1. Receives formatted messages
2. Generates AI response
3. Returns plain text output

---

### 9. Response Return Path

The response flows back:
FastAPI → PHP (api_client.php) → Moodle API (chatbot_api.php) → JS (chatbot.js)

---

### 10. UI Update (Frontend)

📌 File:

- `chatbot.js`

Steps:

1. Receives response JSON
2. Extracts: message, session_id
3. Updates UI:
   - appends assistant message
   - updates session if needed
   - stops loading indicator

---

## 🗄 Data Stored in System

## Session Data

- session_id
- user_id

**Messages**
Each message stored as:

- role: user | assistant
- content: text
- session_id reference

---

## 🔐 Security Layer

Implemented in PHP API client:

- HMAC SHA256 signature
- Timestamp validation
- Request integrity check

Purpose:

- prevent fake requests
- ensure trusted communication between Moodle and backend

---

## 🧠 Key Design Principles

1. **Multi-layer separation**: UI (JS), Middleware (PHP), Backend (Python), AI (LLM)
2. **Stateless backend API**: Each request includes session_id, no global state in backend
3. **Session-based memory**: Context is reconstructed from DB per request
4. **Modular extensibility**: System is designed to support future modules (Analytics, Feedback, Translation, RAG)

---

## 🚧 Current Limitations

- No streaming responses
- No real-time token generation
- Basic session memory only
- No RAG integration yet
- No advanced analytics pipeline

---

## 🎯 Summary

The SDG Campus AI Chat system implements a full end-to-end AI pipeline:
User → Moodle UI → PHP Layer → FastAPI → LLM → Back → UI

It is designed as a scalable foundation for future AI educational modules such as analytics, feedback systems, translation, and RAG-based learning assistance.
