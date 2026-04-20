# ⚙️ Moodle Backend Layer — SDG Campus AI

## 📌 Overview

The Moodle backend layer acts as a **bridge between the frontend (JavaScript UI) and the external AI backend (FastAPI)**.

It is responsible for:

- handling AJAX requests from the frontend
- validating user permissions
- managing chat data in the Moodle database
- forwarding requests to the AI backend
- returning responses back to the UI

---

## 🧩 Architecture Overview

```text
Frontend (chatbot.js)
↓
Moodle External API (chatbot_api.php)
↓
Service Layer (service.php)
↓
API Client (api_client.php)
↓
FastAPI Backend

```

---

## 🔄 Request Flow

### 📤 Sending a Message

```text
User (UI)
↓
chatbot.js (AJAX)
↓
chatbot_api::send_message()
↓
service->send_message()
↓
api_client->post('/chat')
↓
FastAPI (/chat endpoint)
↓
LLM response
↓
Back to Moodle
↓
Saved in DB
↓
Returned to frontend

```

---

## 🧠 Components

---

## 1. 🌐 External API Layer

📌 File: `classes/external/chatbot_api.php`

---

### 🎯 Purpose

Acts as the **entry point for all frontend AJAX requests**.

---

### Key Responsibilities

- validate input parameters
- check user permissions
- enforce Moodle security context
- call internal service layer
- return structured response

---

### send_message()

```php
chatbot_api::send_message($session_id, $message, $course_id)
```

#### Flow

1. Validate parameters
2. Validate context
3. Check capability:

   ```url
   local/ai_system:use_chatbot
   ```

4. Call service:

   ```php
   $service->send_message(...)
   ```

5. Return response

---

### 🔹 get_history()

- retrieves chat history
- returns JSON-encoded messages

---

## 🔐 Security

- `require_login()` enforced earlier (index.php)
- `validate_context()` ensures correct scope
- `require_capability()` restricts access

---

## 2. 🧠 Service Layer

📌 File: `classes/chatbot/service.php`

---

### 🎯 Purpose

Contains **core business logic*- of the chatbot inside Moodle.

---

### 🔹 Responsibilities

- store messages in database
- call external AI backend
- transform responses
- return data to API layer

---

### 🔹 send_message()

#### Step-by-step:

---

#### 1. Save user message

```php
$DB->insert_record('local_ai_system_messages', ...)
```

---

#### 2. Call AI backend

```php
$client->post('/chat', [...])
```

---

#### 3. Log request/response

```php
error_log(...)
```

---

#### 4. Extract AI response

```php
$response['message']
```

---

#### 5. Save AI message

```php
$DB->insert_record(...)
```

---

#### 6. Return result

```php
[
    'message' => ...,
    'session_id' => ...
]
```

---

### 🔹 get_history()

- retrieves messages from DB
- sorts by time
- formats for UI

```php
[
    'role' => 'user | assistant',
    'content' => '...',
    'created_at' => 'HH:mm'
]
```

---

## 🗄 Database Layer

### 📌 Table: `local_ai_system_messages`

---

### Structure (inferred)

| Field      | Description             |
| ---------- | ----------------------- |
| session_id | Chat session identifier |
| role       | user / assistant        |
| content    | Message text            |
| created_at | Timestamp               |

---

### 💡 Notes

- simple structure (MVP)
- no foreign keys (yet)
- no user_id stored → potential improvement

---

## 3. 🔗 API Client Layer

📌 File: `classes/external/api_client.php`

---

### 🎯 Purpose

Handles **communication with FastAPI backend**.

---

### Responsibilities

- build HTTP requests
- sign requests (HMAC)
- send via cURL
- decode responses
- log debug information

---

### Request Example

```php
POST /chat

{
    "session_id": "...",
    "user_id": 123,
    "message": "Hello"
}
```

---

### 🔐 Security Mechanism

#### Headers

```http
X-Timestamp
X-Signature
```

---

#### Signature

```php
hash_hmac('sha256', timestamp + body, secret)
```

---

### Error Handling

```php
if ($curl->get_errno()) {
    throw new moodle_exception(...)
}
```

---

### Logging

- request data
- response data
- errors

Saved into:

```url
/debug.log
```

---

## 🧠 Design Principles

---

### 1. Layered Architecture

- API layer → validation
- Service layer → logic
- Client layer → external communication

---

### 2. Separation of Concerns

| Layer        | Responsibility           |
| ------------ | ------------------------ |
| External API | validation & permissions |
| Service      | business logic           |
| API Client   | HTTP communication       |

---

### 3. Backend as Proxy

Moodle **does not call LLM directly**
→ it delegates to FastAPI backend

---

### 4. Stateless Communication

- session handled via `session_id`
- no persistent connection

---

## 🚧 Current Limitations

- no retry mechanism for API failures
- no timeout handling strategy
- no structured error responses to frontend
- messages table lacks user_id
- no pagination for history
- no caching

---

## 🚀 Future Improvements

---

### 🔐 Security

- validate API signature on backend
- rotate secrets
- add rate limiting

---

### 🧠 Data Model

- add `user_id` to messages
- support multiple conversations per user
- add message metadata

---

### ⚡ Performance

- async queue for LLM calls
- caching responses
- batching requests

---

### 📊 Features

- message editing / regeneration
- feedback on responses
- analytics tracking

---

## 🎯 Summary

The Moodle backend layer is a **middleware system*- that:

- connects frontend with AI backend
- ensures security and validation
- manages chat persistence
- abstracts external API communication

It is designed to be **simple, modular, and extensible**, forming a solid foundation for future AI-powered features within the SDG Campus platform.
