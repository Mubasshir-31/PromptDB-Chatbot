import os
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime

# Load .env variables
load_dotenv()

# MongoDB connection
mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri)

# Database and collections
db = client["PromptDB_Database"]
users_collection = db["users"]
logs_collection = db["logs"]
mcp_collection = db["mcp_sessions"]  # ✅ NEW: MCP collection

# 🔹 Function to search users by city
def get_users_by_city(city):
    return list(users_collection.find(
        {"city": {"$regex": f"^{city}$", "$options": "i"}},  # Case-insensitive match
        {"_id": 0}
    ))

# 🔹 Function to update user's age
def update_user_age(name, new_age):
    result = users_collection.update_one(
        {"name": name},
        {"$set": {"age": new_age}}
    )
    return result.modified_count

# 🔹 Function to log actions to MongoDB and local file
def log_action(action_type, data):
    timestamp = datetime.utcnow()

    # ✅ Log to MongoDB
    logs_collection.insert_one({
        "action": action_type,
        "data": data,
        "timestamp": timestamp
    })

    # ✅ Log to local file
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "action.log")
    log_line = f"[{timestamp.isoformat()}] ACTION: {action_type.upper()} | DATA: {data}\n"
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(log_line)

# 🔹 ✅ MCP: Get session history
def get_session_history(session_id):
    session = mcp_collection.find_one({"session_id": session_id})
    return session["messages"] if session else []

# 🔹 ✅ MCP: Save session history
def save_session_history(session_id, messages):
    mcp_collection.update_one(
        {"session_id": session_id},
        {"$set": {"messages": messages, "last_updated": datetime.utcnow()}},
        upsert=True
    )
