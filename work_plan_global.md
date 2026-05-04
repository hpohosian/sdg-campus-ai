🧠 1. Главная цель рефакторинга

Сейчас у тебя:

/chat  → делает ВСЁ

Ты хочешь:

/sessions        → управление сессиями
/messages        → обмен сообщениями
/chat (опц.)     → legacy / convenience
🏗 2. Новая архитектура (логическая)
🔹 Уровень API (router)
📁 sessions

Отвечает только за сессии:

создать сессию
получить список
обновить (title, course_id)
удалить
📁 messages

Отвечает только за сообщения:

отправить сообщение
получить историю
📁 chat (optional)

Просто shortcut:

“send message + get response”

но внутри он вызывает /messages

🧩 3. Как делится ответственность
❌ Сейчас (плохо)
ChatService:
- session logic
- history
- prompt building
- LLM call
- persistence
✅ После рефакторинга
🔵 SessionService

Отвечает только за:

create session
get session
update session
🔵 MessageService

Отвечает за:

save message
get history
formatting history for LLM
🔵 ChatOrchestrator (новый слой)

Это важно.

Он делает:

1. load session
2. load messages
3. build prompt
4. call LLM
5. save messages
6. return response

👉 Но НЕ владеет БД логикой напрямую

🧠 4. Как переразбить твой текущий ChatService

Твой ChatService сейчас = “монстр”

Мы его делим так:

🔹 ChatService → становится ChatOrchestrator

Оставляет только:

orchestration (flow)
вызов других сервисов
🔹 SessionRepository

Остаётся, но позже станет:

DBSessionRepository
🔹 MessageRepository (у тебя его сейчас нет — надо добавить)

Сейчас у тебя messages внутри session → ❌ плохо

Нужно:

MessageRepository

чтобы:

save_message(session_id, role, content)
get_messages(session_id)

---

# 🔄 5. Новый data flow

## 📩 POST /messages

```text
MessageRouter
   ↓
MessageService
   ↓
ChatOrchestrator
   ↓
LLM
   ↓
MessageRepository (save)
📦 POST /sessions
SessionRouter
   ↓
SessionService
   ↓
SessionRepository
🧪 6. Как упростится Chat logic

Сейчас:

handle_message()

После:

👉 станет просто:

orchestrate_chat(session_id, user_message)
🧱 7. Что нужно добавить в структуру проекта

Ты сейчас:

chatbot/

👉 станет:

chatbot/
├── router/
│   ├── chat_router.py        (optional)
│   ├── session_router.py
│   └── message_router.py
│
├── services/
│   ├── chat_orchestrator.py
│   ├── session_service.py
│   └── message_service.py
│
├── repositories/
│   ├── session_repository.py
│   └── message_repository.py   ← НОВЫЙ
│
├── schemas.py
└── prompts.py
⚠️ 8. Важный момент про твою текущую модель

Сейчас у тебя:

Session.messages: List[ChatMessage]

👉 это ошибка архитектурно

Почему:

messages не должны жить внутри session
это ломает масштабирование
нельзя нормально query делать
✔ правильно:
sessions table
messages table (отдельно)

👉 и ты уже это сделал в Moodle XML — это хорошо

🔥 9. Как это связано с Moodle DB

Ты сейчас в идеальном положении:

👉 Moodle уже имеет:

sessions table
messages table
💡 значит будущая миграция будет лёгкой:

Ты просто заменишь:

InMemoryRepository → MoodleRepository → (потом SQLAlchemy)
🚀 10. Что делаем дальше (следующий шаг)

Если ты согласен с этой архитектурой, дальше я могу:

👉 Шаг 1

Разбить твой текущий ChatService на:

ChatOrchestrator
MessageService
SessionService
👉 Шаг 2

Нарисовать точные endpoints:

/sessions
/messages
/chat (legacy)
👉 Шаг 3

Сказать как мигрировать без поломки фронта Moodle plugin