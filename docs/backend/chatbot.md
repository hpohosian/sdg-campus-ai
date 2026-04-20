# 💬 Chatbot Module — SDG Campus AI Backend

## 📌 Overview

The Chatbot module is the **core intelligence layer** of the SDG Campus AI backend.

It is responsible for:

- handling user messages
- managing chat sessions
- building prompts for LLM
- interacting with the AI model (Mistral)
- storing conversation history

This module implements a **stateful chat system on top of a stateless LLM API**.

---

## 🧩 Module Structure

```text

api/chatbot/
├── router.py              # HTTP API layer
├── service.py             # business logic (ChatService)
├── schemas.py             # data models (Pydantic)
├── session_repository.py  # in-memory session storage
└── prompts.py             # system prompt templates
```

---

## 🌐 API Layer (router.py)

📌 File: `router.py`

### Purpose

Defines the HTTP endpoint for chatbot communication.

---

### Endpoint

```url
POST /chat
```

---

### Flow

- Receives `ChatRequest`
- Injects `ChatService` via FastAPI dependency system
- Calls `handle_message()`
- Returns `ChatResponse`

---

### Responsibility

- No business logic
- Only request routing
- Delegation to service layer

---

## 🧠 Data Models (schemas.py)

📌 File: `schemas.py`

Defines structured communication between frontend and backend.

---

### ChatRequest

```python id="chat_request_model"
class ChatRequest(BaseModel):
    session_id: str
    user_id: int
    message: str
    course_id: Optional[int] = None
```

### Purpose

- identifies user session
- carries user message
- optionally includes course context

---

### ChatMessage

```python id="chat_message_model"
class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
```

### Purpose

- unified message format for LLM and storage

---

### ChatResponse

```python
class ChatResponse(BaseModel):
    session_id: str
    message: str
```

### Purpose

- returns AI-generated response to frontend

---

## 🧠 Core Logic (service.py)

📌 File: `service.py`

This is the **central orchestrator of the chatbot system**.

---

## 🔄 Main Flow: handle_message()

```python
async def handle_message(self, request: ChatRequest)
```

---

### Step 1 — Session management

```python
session = await self.session_repo.get_or_create(
    request.session_id,
    request.user_id
)
```

### Purpose

- ensures session exists
- creates new session if needed

---

### Step 2 — Load message history

```python
history = await self.session_repo.get_messages(session.id)
```

### Purpose

- retrieves previous conversation
- provides context for LLM

---

### Step 3 — Build LLM messages

```python
messages = self._build_messages(history, request.message)
```

---

### Internal logic

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    ...history,
    {"role": "user", "content": new_message}
]
```

### Purpose

- system prompt defines behavior
- history provides context
- user message triggers response

---

## 🤖 Step 4 — LLM call

```python
response_text = await self.llm.chat(messages)
```

### Purpose

- sends structured prompt to Mistral model
- receives generated response text

---

## 💾 Step 5 — Save conversation

```python
await self.session_repo.save_message(session.id, "user", request.message)
await self.session_repo.save_message(session.id, "assistant", response_text)
```

### Purpose

- persists full conversation history
- enables future context reconstruction

---

## 📤 Step 6 — Response

```python
return ChatResponse(
    session_id=session.id,
    message=response_text
)
```

---

## 🧾 Prompts System (prompts.py)

📌 File: `prompts.py`

### SYSTEM_PROMPT

Defines global AI behavior:

```text
You are an AI tutor.

Your task is to help students understand topics step by step.

Rules:
- Explain simply
- Use examples
- Be clear and structured
- If something is unclear, ask a question
```

---

### Additional prompt variants

#### Explain mode

```text
Explain the topic step by step in simple terms.
```

#### Short mode

```text
Answer briefly in 2-3 sentences.
```

#### Tutor mode

```text
You are a strict but helpful tutor.

- Ask questions
- Guide the student
- Do not give direct answers immediately
```

---

### Purpose of prompt system

- defines AI behavior styles
- enables future multi-mode chatbot
- supports adaptive tutoring logic

---

## Session Storage (session_repository.py)

📌 File: `session_repository.py`

### Type: In-memory storage (MVP)

---

## 🧩 Data Model

### Session

```python
class Session:
    def __init__(self, session_id: str, user_id: int):
        self.id = session_id
        self.user_id = user_id
        self.messages = []
```

---

## 📦 Responsibilities

### SessionRepository handles

- session creation
- message storage
- message retrieval

---

## 🔄 Methods

### 1. get_or_create()

```python
async def get_or_create(session_id, user_id)
```

- returns existing session OR creates new one

---

### 2. get_messages()

```python
async def get_messages(session_id)
```

- returns full chat history
- used for LLM context building

---

### 3. save_message()

```python
async def save_message(session_id, role, content)
```

- stores user/assistant messages
- appends to session history

---

## 🔄 End-to-End Chat Flow

```text
User (Moodle UI)
    ↓
router.py (/chat)
    ↓
ChatService.handle_message()
    ↓
SessionRepository (load/create session)
    ↓
Load message history
    ↓
Build prompt (system + history + user)
    ↓
LLM.chat()
    ↓
Save messages
    ↓
Return ChatResponse
```

---

## 🧠 Design Principles

### 1. Layered architecture

- router → service → repository → LLM

---

### 2. Stateless API design

- backend does not store runtime memory
- session_id restores context

---

### 3. Prompt-driven behavior

- system prompt defines AI personality
- modular prompt system allows behavior switching

---

### 4. Separation of concerns

- API layer (router)
- logic layer (service)
- storage layer (repository)
- AI layer (LLM)

---

## 🚧 Current Limitations

- Session storage is in-memory (not persistent)
- No database integration yet
- No message pagination
- No streaming responses
- No advanced memory optimization

---

## 🚀 Future Improvements

### Persistent storage

- move sessions to database
- enable scaling across servers

---

### 🌊 Streaming responses

- real-time token output
- improved UX in frontend

---

### 🧠 Advanced memory

- long-term user context
- personalized tutoring behavior

---

### 📊 Analytics integration

- track learning behavior
- measure engagement

---

## 🎯 Summary

The Chatbot module is the **core conversational engine** of SDG Campus AI.

It implements:

- session-based memory
- prompt-driven AI behavior
- structured LLM interaction
- modular and extensible architecture

It acts as the foundation for all future AI features in the system.
