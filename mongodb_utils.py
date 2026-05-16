from datetime import UTC, datetime
import os

from dotenv import load_dotenv
from pymongo import MongoClient


load_dotenv()

mongo_client = None


def get_database():
    global mongo_client

    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise RuntimeError("MONGO_URI is missing in .env.")

    if mongo_client is None:
        mongo_client = MongoClient(
            mongo_uri,
            connectTimeoutMS=5000,
            serverSelectionTimeoutMS=5000,
        )

    return mongo_client["PromptDB_Database"]


def get_collections():
    db = get_database()
    return db["users"], db["logs"], db["sessions"]


def get_users_by_city(city):
    users_collection, _, _ = get_collections()
    return list(users_collection.find(
        {"city": {"$regex": f"^{city}$", "$options": "i"}},
        {"_id": 0},
    ))


def update_user_age(name, new_age):
    users_collection, _, _ = get_collections()
    result = users_collection.update_one(
        {"name": name},
        {"$set": {"age": new_age}},
    )
    return result.modified_count


def log_action(action_type, data):
    _, logs_collection, _ = get_collections()
    timestamp = datetime.now(UTC)

    logs_collection.insert_one({
        "action": action_type,
        "data": data,
        "timestamp": timestamp,
    })

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "action.log")
    log_line = f"[{timestamp.isoformat()}] ACTION: {action_type.upper()} | DATA: {data}\n"
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(log_line)


def get_session_history(session_id):
    _, _, sessions_collection = get_collections()
    session = sessions_collection.find_one({"session_id": session_id})
    return session["messages"] if session else []


def save_session_history(session_id, messages):
    _, _, sessions_collection = get_collections()
    sessions_collection.update_one(
        {"session_id": session_id},
        {"$set": {"messages": messages, "last_updated": datetime.now(UTC)}},
        upsert=True,
    )
