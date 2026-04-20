# 🌐 API Reference — SDG Campus AI Backend

## 📌 Overview

This document describes the HTTP API of the SDG Campus AI backend.

The API is built using **FastAPI** and serves as the communication layer between:

- Moodle plugin (PHP + JavaScript frontend)
- AI backend (ChatService + LLM)
- session storage system

All endpoints are designed to be **stateless and session-based** using `session_id`.

---

## 🧩 Base URL

```url
[http://127.0.0.1:8001](http://127.0.0.1:8001)

```

---

## 🔐 Authentication & Security

Currently, the API uses a **lightweight signature-based mechanism** for internal communication.

### Headers used

- `X-Timestamp` — request timestamp
- `X-Signature` — HMAC SHA256 signature

This ensures that only trusted clients (Moodle plugin) can communicate with the backend.

---

## 💬 Chat API

---

## 📍 POST `/chat`

### 📌 Description

Main endpoint for interacting with the AI chatbot.

Handles:

- session management
- message processing
- LLM response generation
- conversation persistence

---

### 📥 Request Body

```json
{
  "session_id": "chat_123456",
  "user_id": 42,
  "message": "Explain what Python is"
}
```

### 🔹 Fields

| Field      | Type    | Description                    |
| ---------- | ------- | ------------------------------ |
| session_id | string  | Unique chat session identifier |
| user_id    | integer | ID of the user                 |
| message    | string  | User input message             |

---

### 📤 Response

```json
{
  "session_id": "chat_123456",
  "message": "Python is a high-level programming language..."
}
```

### 🔹 Fields

| Field      | Type   | Description           |
| ---------- | ------ | --------------------- |
| session_id | string | Active session ID     |
| message    | string | AI-generated response |

---

## 🔄 Request Flow

When a request is sent to `/chat`, the following happens:

```
Client (Moodle)
    ↓
FastAPI Router (router.py)
    ↓
ChatService (service.py)
    ↓
Session Repository (history load/save)
    ↓
LLM Layer (Mistral)
    ↓
Response returned
```

---

## 🧠 API Design Principles

### 1. Stateless Communication

- Backend does not store runtime state
- All context is passed via `session_id`

---

### 2. Session-based Memory

- Conversation history is stored in database
- Each request reconstructs context from stored messages

---

### 3. Thin API Layer

- API only handles validation and routing
- Business logic is delegated to `ChatService`

---

### 4. Model Agnostic Design

- API does not depend on specific LLM (Mistral is internal detail)
- LLM is abstracted via `BaseLLM`

---

## 🧩 Internal Integration

The `/chat` endpoint internally interacts with:

### ChatService

- orchestrates message processing
- builds prompts
- calls LLM

### SessionRepository

- stores and retrieves chat history
- manages session lifecycle

### LLM Layer

- generates AI responses
- currently implemented via Mistral

---

## 🚧 Current Limitations

- No rate limiting
- No request throttling
- No streaming responses
- No pagination for chat history
- No public API versioning

---

## 🚀 Future Extensions

### 📡 Streaming API

- `/chat/stream`
- real-time token output

---

### 📊 Analytics API

- `/analytics`
- user interaction tracking

---

### 💬 Feedback API

- `/feedback`
- response rating system

---

### 🌍 Translation API

- `/translate`
- multilingual support for course content

---

## 🎯 Summary

The SDG Campus AI API is a **minimal but extensible communication layer** designed to:

- connect Moodle frontend with AI backend
- manage chat sessions
- provide structured AI responses
- serve as a foundation for future AI-driven endpoints

It is intentionally lightweight to ensure **scalability and modularity** for future system expansion.
