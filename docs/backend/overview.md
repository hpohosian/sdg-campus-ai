# ⚙️ Backend Overview — SDG Campus AI

## 🔗 Backend Documentation Navigation

- 📌 [General Architecture](../architecture.md)
- 🔄 [Data Flow](../data-flow.md)
- 💬 [Chatbot Module](chatbot.md)
- 🧠 [LLM Layer](llm.md)
- 📡 [API Reference](api.md)

---

## 📌 Overview

The backend of the SDG Campus AI system is built using **FastAPI (Python)** and serves as the core processing layer for all AI-related functionality.

It acts as a bridge between:

- Moodle plugin (PHP/JS frontend)
- LLM layer (Mistral)
- session storage and business logic

The backend is designed to be **modular, stateless, and scalable**.

---

## 🏗 High-Level Backend Structure

```text
api/
├── main.py              # Application entry point
├── dependencies.py      # Dependency injection system
├── chatbot/             # Chat system module
├── llm/                 # LLM abstraction layer
├── middleware/          # (future) auth, logging, etc.
└── settings.py          # configuration

```

---

## 🚀 Application Entry Point

📌 `main.py`

The backend is initialized here.

### Responsibilities

- Creates FastAPI application instance
- Configures CORS middleware
- Registers routers
- Connects all modules into a single API service

### Key logic

- Enables communication with Moodle frontend via CORS
- Registers chatbot API endpoints

### Included modules

- `chatbot_router`

---

## 🌐 API Layer

The backend exposes a REST API using FastAPI routers.

### Main endpoint group

- `/chat` → handled by chatbot module

All endpoints are grouped and injected into the main application via:

```python
app.include_router(chatbot_router)
```

---

## 🔌 Dependency Injection System

📌 `dependencies.py`

The system uses **FastAPI dependency injection** to manage core services.

### Purpose

- Decouple business logic from instantiation
- Provide reusable singleton-like services
- Improve testability and modularity

---

## 🧠 Core Dependencies

### 1. Settings

```python
get_settings()
```

- Cached configuration provider
- Stores API keys and environment settings
- Uses `@lru_cache` for performance

---

### 2. Session Repository

```python
get_session_repository()
```

- Handles chat session storage
- Provides access to message history
- Abstracts database layer

---

### 3. LLM Provider

```python
get_llm()
```

- Returns implementation of `BaseLLM`
- Currently uses `MistralLLM`
- Configured with API key from settings

---

### 4. Chat Service

```python
get_chat_service()
```

- Core business logic layer
- Combines:

  - LLM
  - session repository
- Handles full message lifecycle

---

## 🧩 Backend Modules

### 💬 Chatbot Module

Responsible for all chat-related logic:

- request handling
- session management
- message processing
- LLM interaction

### 🤖 LLM Module

Abstract layer for AI models:

- `BaseLLM` → interface
- `MistralLLM` → implementation

This design allows future replacement of the model without changing business logic.

---

## 🔄 Request Flow (Backend Level)

1. Request arrives from Moodle plugin
2. FastAPI receives request via `/chat` endpoint
3. Dependency injection provides `ChatService`
4. ChatService:

   - loads session
   - loads message history
   - builds prompt
5. LLM is called (Mistral)
6. Response is generated
7. Message is stored in session repository
8. Response is returned to API layer

---

## 🧠 Design Principles

### 1. Modularity

Each system component is isolated:

- chatbot logic
- LLM layer
- session storage

---

### 2. Dependency Injection

All services are injected, not hardcoded:

- improves testability
- improves flexibility
- reduces coupling

---

### 3. Stateless API Design

- backend does not store runtime state
- all context comes from `session_id`

---

### 4. LLM Abstraction

- system is not tied to Mistral
- any model can replace it via `BaseLLM`

---

## 🚧 Current Limitations

- No middleware layer implemented yet (auth/logging)
- No caching system for LLM responses
- Session repository is basic
- No async queue / background processing
- No observability (metrics/logging system)

---

## 🚀 Future Improvements

### 🔐 Middleware

- authentication layer
- request validation
- logging system

---

### 🧠 AI Enhancements

- RAG integration (course-aware responses)
- long-term memory system
- personalization layer

---

### 📊 Observability

- logging pipeline
- request tracking
- analytics module integration

---

## 🎯 Summary

The SDG Campus AI backend is a **clean FastAPI-based modular system** designed around:

- separation of concerns
- dependency injection
- scalable AI integration
- future extensibility for advanced AI features

It serves as the **core intelligence layer** of the entire platform.
