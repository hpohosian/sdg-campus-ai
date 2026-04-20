# 🏗 Architecture — SDG Campus AI Modules

## 📌 Overview

SDG Campus AI Modules is a modular AI system integrated into the **SDG Campus (Moodle-based platform)**.  
The architecture is designed to separate responsibilities between the **frontend (Moodle plugin)**, the **backend (FastAPI service)**, and the **AI layer (LLM)**.

The system follows a **client → middleware → AI backend → response pipeline** approach.

---

## 🧩 High-Level Architecture

```text
[Moodle UI (JS + PHP)]
        ↓
[Moodle Plugin (PHP)]
        ↓
[FastAPI Backend (Python)]
        ↓
[LLM Layer (Mistral)]
        ↓
[Response Processing]
        ↓
    [Moodle UI]
```

---

## 🔌 System Components

### 1. 🎓 Moodle Plugin (Frontend + Integration Layer)

**Location:**
moodle-plugin/local/ai_system/

**Responsibilities:**

- Provides chat UI inside Moodle
- Handles user interactions (sending/receiving messages)
- Communicates with backend API via HTTP requests
- Renders AI responses in the interface

**Key parts:**

- `index.php` — entry point for plugin page
- `amd/src/chatbot.js` — frontend logic (AJAX requests, UI updates)
- `templates/chatbot.mustache` — UI template

**Role in architecture:**
Acts as a bridge between Moodle and AI system.

---

### 2. ⚙️ Backend API (FastAPI - Python Core)

**Location:**
api/chatbot/
api/llm/
api/middleware/

**Responsibilities:**

- Receives requests from Moodle plugin
- Manages chat sessions (`session_id`)
- Processes messages
- Calls LLM (Mistral)
- Returns generated responses
- Stores chat history in database

**Core modules:**

🧠 Chatbot Layer

- `router.py` — API endpoints (`/chat`)
- `service.py` — business logic (message processing)
- `schemas.py` — request/response models
- `session_repository.py` — session handling
- `prompts.py` — list of prompts

🧩 Middleware

- `auth.py` — authentication / access control

🧠 LLM Layer

- `mistral.py` — integration with Mistral model
- `base.py` — abstraction for LLM providers

---

### 3. 🤖 LLM Layer (AI Engine)

**Current implementation:**

- Mistral model (via API or local inference)

**Responsibilities:**

- Generate responses based on user input
- (Future) use context from:
  - chat history
  - course materials (RAG system)

**Planned upgrade:**

- Retrieval-Augmented Generation (RAG)
- Course-aware responses
- Personalized tutoring behavior

---

### 4. 🗄 Data Storage

**Current state:**

- Basic database storing:
  - user messages
  - assistant responses
  - session IDs

**Data model concept:**
User → Session → Messages

**Purpose:**

- Maintain conversation history
- Enable context-aware responses
- Support analytics (future module)

---

## 🔄 Data Flow (Detailed)

1. User writes a message in Moodle chat UI
2. `chatbot.js` captures input
3. Request is sent to `index.php` (Moodle plugin backend)
4. PHP plugin forwards request to FastAPI endpoint
5. FastAPI `router.py` receives request
6. `service.py` processes message:
   - validates input
   - loads session context
7. Message is sent to LLM layer (`mistral.py`)
8. LLM generates response
9. Response is stored in database
10. API returns result to Moodle plugin
11. UI displays AI response

---

## 🧠 Design Principles

### 1. Separation of concerns

- UI (Moodle)
- Backend (FastAPI)
- AI (LLM)

Each layer is independent and replaceable.

---

### 2. Stateless API design

- Each request uses `session_id`
- Backend does not rely on global state

---

### 3. Modular architecture

- Chatbot, analytics, translation, feedback are separate modules
- Easy to extend system without rewriting core logic

---

### 4. Scalable AI integration

- LLM layer is abstracted
- Future models can replace Mistral without changing core logic

---

## 🚧 Current Limitations

- No RAG system yet (only basic LLM responses)
- Limited analytics
- Basic session memory
- No long-term personalization

---

## 🚀 Future Architecture Extensions

### 🧠 RAG System

- connect AI to course materials
- vector database (planned)
- semantic search for context retrieval

### 📊 Analytics Module

- track student interactions
- learning behavior analysis
- performance insights

### 💬 Feedback System

- collect user feedback on answers
- improve response quality

### 🌍 Translation Module

- multilingual support
- automatic translation of course content

---

## 🎯 Summary

The system is designed as a **modular AI layer on top of Moodle**, allowing:

- scalable AI features
- easy extension of functionality
- separation between education platform and AI logic
- future integration of advanced AI techniques (RAG, personalization, analytics)
