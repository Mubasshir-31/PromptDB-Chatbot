
# PromptDB Chatbot 🧠💬

A smart AI-powered chatbot built with Python, Flask, OpenRouter, and MongoDB.
It allows natural language queries like:

- "Show users from Delhi"
- "Add Raj, age 25, from Noida"
- "Update Rahul's age to 30"

## Features

- Natural language to MongoDB queries (via OpenRouter)
- CRUD support: Insert, Find, Update, Delete
- Session memory (MCP) stored in MongoDB
- Dual logging: MongoDB + action.log
- Clear, timestamped chat UI

## 📦 Setup Instructions

### 1. Clone and Setup

```bash
git clone https://github.com/your-username/promptdb-chatbot.git
cd promptdb-chatbot
cp .env.example .env  # Fill your secrets here

# Tech Stack
Python, Flask
MongoDB (Atlas)
OpenRouter (Mistral AI)
HTML/CSS/JS frontend

# This project is copyright © Mohd Mubasshir Khan, and is shared for reference only. Please do not copy or reuse without permission.
