# 🤖 LLM Layer — SDG Campus AI Backend

## 📌 Overview

The LLM layer is responsible for all interactions with Large Language Models (LLMs) in the SDG Campus AI system.

It provides an **abstraction layer over different AI providers**, allowing the system to:

- switch models without changing business logic
- support multiple LLM providers
- enable future features like streaming and RAG

---

## 🧩 Module Structure

```text
api/llm/
├── base.py        # Abstract LLM interface
└── mistral.py     # Mistral implementation
```

---

## 🧠 Architecture Concept

The system uses a **provider-agnostic LLM abstraction layer**.

Instead of calling Mistral directly from business logic, the system uses:

```text
ChatService → BaseLLM → MistralLLM → Mistral API
```

This ensures:

- loose coupling
- testability
- future extensibility

---

## 🔌 Base LLM Interface (base.py)

📌 File: `base.py`

### Purpose

Defines a **unified contract** for all LLM providers.

---

### Core Methods

#### 1. chat()

```python id="llm_base_chat"
async def chat(self, messages, **kwargs) -> str
```

### Responsibility

- Takes structured message history
- Returns full model response as string

### Input format

```json
[
  {"role": "system", "content": "..."},
  {"role": "user", "content": "..."}
]
```

---

#### 2. stream()

```python
async def stream(self, messages, **kwargs) -> AsyncIterator[str]
```

### Responsibility

- Streams response chunks from model
- Designed for future real-time UI updates

### Current state

- Not fully implemented (placeholder behavior)

---

## 🤖 Mistral Implementation (mistral.py)

📌 File: `mistral.py`

### Purpose

Concrete implementation of `BaseLLM` using **Mistral AI API**.

---

## ⚙️ Initialization

```python
def __init__(self, api_key=None, model=None)
```

### Behavior

- Loads API key from parameters or settings
- Validates API key presence
- Sets model name from config
- Initializes Mistral client

### Key dependency

- `mistralai.client.Mistral`

---

## 💬 chat() Implementation

```python
async def chat(self, messages, **kwargs) -> str
```

### Flow

1. Sends request to Mistral API:

```python
self.client.chat.complete(
    model=self.model,
    messages=messages
)
```

2. Validates response:

- ensures choices exist
- ensures content is not empty

3. Returns:

- raw text response from model

---

### Output

```json
{
  "message": "AI generated response text"
}
```

---

## 🌊 stream() Implementation

```python
async def stream(self, messages, **kwargs)
```

### Current behavior

- Calls `chat()` internally
- Returns full response as a single chunk

### Purpose

- Placeholder for future streaming API support

---

## 🧠 Design Principles

### 1. Abstraction Layer

- Business logic does not depend on Mistral directly
- Uses `BaseLLM` interface

---

### 2. Provider Independence

The system can support:

- Mistral (current)
- OpenAI
- local models
- future fine-tuned models

without changing ChatService.

---

### 3. Async Ready Design

- All methods are async
- prepared for high-concurrency usage
- compatible with FastAPI architecture

---

### 4. Extensibility

The architecture is designed to support:

- streaming responses
- function calling
- tool usage
- RAG-enhanced prompts

---

## 🔄 LLM Request Flow

```text
ChatService
    ↓
BaseLLM.chat()
    ↓
MistralLLM.chat()
    ↓
Mistral API request
    ↓
Response validation
    ↓
Return text to service layer
```

---

## 🚧 Current Limitations

- Streaming is not fully implemented
- No retry logic for failed API calls
- No token usage tracking
- No caching layer for repeated queries
- No fallback model support

---

## 🚀 Future Improvements

### 🌊 Streaming Mode

- real-time token output
- integration with frontend typing effect

---

### 🔁 Multi-Provider Support

- OpenAI integration
- local LLM support (Ollama, etc.)

---

### 🧠 RAG Integration Hook

- inject external knowledge into prompts
- course-aware responses

---

### 📊 Monitoring Layer

- token usage tracking
- latency monitoring
- cost estimation

---

## 🎯 Summary

The LLM layer is a **provider-agnostic abstraction system** that isolates AI logic from business logic.

It ensures:

- flexibility in model selection
- clean architecture separation
- future scalability for advanced AI features

Currently powered by Mistral, but designed to support **any LLM provider in the future without changes to core system logic**.
