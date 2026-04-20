# SDG Campus AI Modules

AI-powered extension modules for the **SDG Campus** educational platform.

## 📌 Overview

This project provides a set of AI-driven modules designed to enhance the learning experience on the SDG Campus platform (based on Moodle).

The system is intended for **students and teachers**, integrating intelligent tools directly into the learning environment — starting with an AI chatbot and expanding into additional educational features.

---

## 🔗 Quick Navigation

- 🧠 [Architecture](docs/architecture.md)
- 💬 [Chatbot Module](docs/backend/chatbot.md)
- 🔌 [Moodle Integration](docs/moodle/overview.md)
- 🚀 [Setup Guide](docs/setup/installation.md)

---

## 🚀 Current Status

The project is in an early development stage.

### ✅ Implemented

- AI Chatbot integrated into Moodle
- End-to-end message flow:

  - User sends a message from the platform
  - Request is sent to the backend (FastAPI)
  - Response is generated via LLM (Mistral)
  - Answer is returned and displayed in the UI
- Session support (`session_id`)
- Basic database for storing chat messages

### 🚧 In Progress / Planned

- AI Analytics module
- Feedback system
- Translation module
- Retrieval-Augmented Generation (RAG) based on course materials
- Improved context awareness and memory

---

## 🧠 Features

### 💬 AI Chatbot

- Interactive chat inside Moodle
- Context-based conversations (sessions)
- LLM-powered responses

### 🔌 Platform Integration

- Seamless integration with Moodle via a custom plugin
- Communication between PHP (Moodle) and Python (FastAPI backend)

---

## 🏗 Architecture

The system consists of two main parts:

- **Moodle Plugin (PHP + JavaScript)**
  Handles UI, user interaction, and communication with backend

- **Backend API (Python / FastAPI)**
  Processes requests, manages sessions, and communicates with the LLM

- **LLM Layer (Mistral)**
  Generates AI responses

---

## 🔄 Data Flow

1. User sends a message in Moodle UI
2. JavaScript sends request to Moodle backend (PHP)
3. PHP plugin forwards request to FastAPI API
4. Backend processes the request and calls the LLM
5. LLM generates a response
6. Response is returned back through the chain to the UI

---

## 🛠 Tech Stack

- **Backend:** FastAPI (Python)
- **LLM:** Mistral
- **Frontend:** JavaScript (Moodle AMD modules)
- **Platform:** Moodle (PHP)
- **Database:** (basic message storage)

---

## 📚 Documentation

Full documentation is available in the `/docs` folder:

### 🧠 Core system

- [Architecture](docs/architecture.md)
- [Data Flow](docs/data-flow.md)

### ⚙️ Backend (Python)

- [Chatbot module](docs/backend/chatbot.md)
- [LLM layer](docs/backend/llm.md)

### 🔌 Moodle Plugin

- [Plugin overview](docs/moodle/overview.md)
- [Frontend integration](docs/moodle/frontend.md)

### 🚀 Setup

- [Installation](docs/setup/installation.md)
- [Run project](docs/setup/run.md)

---

## 🎯 Goal

The main goal of this project is to build a modular AI system that enhances the educational process by providing:

- intelligent assistance
- AI translator
- automated analysis
- personalized feedback
- access to course-based knowledge via AI (RAG)

---

## ⚠️ Note

This is an early-stage prototype and is actively evolving.
