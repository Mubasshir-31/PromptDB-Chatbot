# PromptDB

Live Demo: https://promptdb-chatbot-fwnj.onrender.com

PromptDB is a secure AI-powered MongoDB console. It converts natural language into validated database commands, previews write operations before execution, and provides user management, audit logs, and data export tools.

## Features

- Admin login with Flask sessions
- Natural language to MongoDB CRUD commands
- Command preview before execution
- Confirmation for insert, update, and delete
- Users dashboard with create, edit, delete, search, and sort
- Audit log dashboard
- CSV and JSON export
- Service status checks for Flask, MongoDB, and OpenRouter
- Responsive UI using the project palette: light gray, dark navy, steel blue, and sand gold

## Tech Stack

- Python
- Flask
- MongoDB Atlas
- OpenRouter
- HTML, CSS, JavaScript

## Local Setup

```powershell
cd e:\Projects\PromptDB
uv python install 3.13
uv venv --python 3.13 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.\.venv\Scripts\Activate.ps1
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Environment Variables

Create `.env` in the project root:

```env
MONGO_URI=your-mongodb-uri
OPENROUTER_API_KEY=your-openrouter-api-key
OPENROUTER_MODEL=openrouter/free
FLASK_SECRET_KEY=your-long-random-secret
ADMIN_USERNAME=PromptDB
ADMIN_PASSWORD=PromptDatabase
```

Do not commit `.env`.

## Login

```text
Username: PromptDB
Password: PromptDatabase
```

## Main Routes

```text
/login
/
/users
/logs
/features
/about
/contact
```

## API Routes

```text
GET    /health
GET    /api/status
GET    /api/examples
POST   /api/preview
POST   /chat
GET    /api/users
POST   /api/users
PATCH  /api/users/:id
DELETE /api/users/:id
GET    /api/logs
GET    /api/export/users.csv
GET    /api/export/users.json
```

## GitHub Push Checklist

Confirm ignored files:

```powershell
git check-ignore -v .env
git check-ignore -v .venv
git check-ignore -v logs/action.log
```

Check what will be committed:

```powershell
git status --short
```

If `.env` appears, remove it from tracking:

```powershell
git rm --cached .env
```

Commit and push:

```powershell
git add .gitignore .env.example README.md app.py mongodb_utils.py insert_sample_users.py static templates requirements.txt
git commit -m "Finalize PromptDB dashboard"
git branch -M main
git remote set-url origin https://github.com/Mubasshir-31/PromptDB-Chatbot.git
git push -u origin main
```

## Resume Bullet

Built PromptDB, a Flask and MongoDB AI console that converts natural language into validated CRUD commands with write previews, admin authentication, audit logs, CSV/JSON export, and a responsive dashboard UI.
