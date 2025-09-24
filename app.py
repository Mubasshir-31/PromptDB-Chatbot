from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import os
from dotenv import load_dotenv
from pymongo import MongoClient
import json
from datetime import datetime

load_dotenv()

mongo_uri = os.getenv("MONGO_URI")
# print(f"DEBUG: MONGO_URI is -> {mongo_uri}")
session_client = MongoClient(mongo_uri)

# ✅ Check required environment variables
if not os.getenv("MONGO_URI") or not os.getenv("OPENROUTER_API_KEY"):
    raise EnvironmentError("Missing MONGO_URI or OPENROUTER_API_KEY in environment variables.")

app = Flask(__name__)

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

mongo_uri = os.getenv("MONGO_URI")
session_client = MongoClient(mongo_uri)
session_db = session_client["PromptDB_Database"]
sessions_collection = session_db["sessions"]
users_collection = session_db["users"]

# ✅ Helper function to log actions
def log_action(action_type, details):
    log_entry = {
        "timestamp": datetime.utcnow(),
        "action_type": action_type,
        "details": details
    }
    # In a real app, you would save this to a log collection or file
    print(f"✅ LOG: {log_entry}")

# ✅ Validate user input for insert
def validate_user_document_insert(doc):
    if not isinstance(doc, dict):
        return False
    required_fields = {"name": str, "age": int, "city": str}
    for field, expected_type in required_fields.items():
        if field not in doc or not isinstance(doc[field], expected_type):
            return False
    return True

# ✅ Validate user input for update (at least one valid field)
def validate_user_document_update(doc):
    if not isinstance(doc, dict) or not doc:
        return False
    allowed_fields = {"name": str, "age": int, "city": str}
    for field, value in doc.items():
        if field not in allowed_fields or not isinstance(value, allowed_fields[field]):
            return False
    return True

@app.route("/")
def home():
    return render_template("index.html")

# ✅ New routes for About, Features, and Contact pages
@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/features")
def features():
    return render_template("features.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json["message"].strip()
    session_id = request.json.get("session_id", "default")

    # ✅ Check for conversational greetings before calling AI
    user_message_lower = user_message.lower()
    if user_message_lower in ["hello", "hi", "hey"]:
        return jsonify({"response": "Hello! I am PromptDB, a database command generator. How can I help you?"})

    if len(user_message) > 500:
        return jsonify({"response": "Your message is too long. Please keep it under 500 characters."})

    try:
        session_doc = sessions_collection.find_one({"session_id": session_id})
        message_history = session_doc["messages"] if session_doc else []
        message_history.append({"role": "user", "content": user_message})

        system_prompt = {
            "role": "system",
            "content": (
                "You are a JSON command generator for MongoDB operations. "
                "Convert natural language instructions into JSON MongoDB-like commands. "
                "NEVER explain anything. Your entire response should be a single valid JSON object only.\n\n"
                "✅ Required keys in output:\n"
                "- 'action': 'find', 'insert', 'update', 'delete'\n"
                "- 'collection': 'users'\n"
                "- Optional: 'filter', 'update', 'document', 'sort', 'limit'\n\n"
                "✅ Field names:\n"
                "- Use only 'name', 'age', 'city'\n"
                "- For birth year, use 'birth_year' which backend converts to 'age'\n\n"
                "✅ Interpret natural expressions:\n"
                "- 'older than 25' → { 'age': { '$gt': 25 } }\n"
                "- 'younger than 18' → { 'age': { '$lt': 18 } }\n"
                "- 'users in Noida or Delhi' → { 'city': { '$in': ['Noida', 'Delhi'] } }\n"
                "- 'youngest users' → { 'sort': { 'age': 1 } }\n"
                "- 'oldest user' → { 'sort': { 'age': -1 }, 'limit': 1 }\n"
                "- 'last 5 users' → { 'sort': { '_id': -1 }, 'limit': 5 }\n"
                "⚠️ Never use aggregation, count, or natural text. Only output valid JSON command."
            )
        }

        messages = [system_prompt] + message_history[-5:]

        ai_response = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=messages
        )

        ai_raw = ai_response.choices[0].message.content.strip()
        print("📤 AI RAW OUTPUT:", ai_raw)

        try:
            fixed_text = ai_raw.replace("'", '"').replace("“", '"').replace("”", '"')
            command = json.loads(fixed_text)
        except json.JSONDecodeError:
            return jsonify({"response": "Sorry, I couldn't understand that request. Please try again."})

        print("🧠 AI Parsed Command:", command)

        action = command.get("action")
        collection = command.get("collection")
        filter_data = command.get("filter", {})
        update_data = command.get("update", {})
        new_doc = command.get("document", {})
        sort_option = command.get("sort")
        limit_option = command.get("limit")

        allowed_fields = {"name", "age", "city"}
        allowed_operators = {"$gt", "$lt", "$in", "$regex", "$options"}
        def is_valid_filter(data):
            if isinstance(data, dict):
                for key in data:
                    if key not in allowed_fields and key not in allowed_operators:
                        return False
                    if isinstance(data[key], dict):
                        if not is_valid_filter(data[key]):
                            return False
            return True

        if not is_valid_filter(filter_data):
            return jsonify({"response": "Invalid field used in filter. Only name, age, city, and allowed operators are permitted."})
        if collection != "users":
            return jsonify({"response": "Only 'users' collection is supported."})

        # ✅ Handle FIND
        if action == "find":
            try:
                if "city" in filter_data:
                    city_val = filter_data["city"]
                    if isinstance(city_val, str):
                        filter_data["city"] = {"$regex": f"^{city_val}$", "$options": "i"}
                    elif isinstance(city_val, dict) and "$in" in city_val:
                        filter_data["city"]["$in"] = [c.strip() for c in city_val["$in"]]

                cursor = users_collection.find(filter_data, {"_id": 0})
                if sort_option:
                    field, direction = list(sort_option.items())[0]
                    cursor = cursor.sort(field, direction)
                if limit_option:
                    cursor = cursor.limit(limit_option)

                results = list(cursor)
            except Exception as e:
                return jsonify({"response": f"MongoDB error: {str(e)}"})

            message_history.append({"role": "assistant", "content": ai_raw})
            sessions_collection.update_one(
                {"session_id": session_id},
                {"$set": {"messages": message_history, "last_updated": datetime.utcnow()}},
                upsert=True
            )

            if "how many" in user_message_lower:
                count = len(results)
                cities = ""
                if "city" in filter_data:
                    if "$regex" in filter_data["city"]:
                        cities = f" in {filter_data['city']['$regex'].strip('^$')}"
                    elif "$in" in filter_data["city"]:
                        cities = f" in {', '.join(filter_data['city']['$in'])}"
                return jsonify({"response": f"There {'is' if count == 1 else 'are'} {count} user{'s' if count != 1 else ''}{cities}."})

            return jsonify({"response": results if results else "No matching records found."})

        # ✅ Handle UPDATE
        elif action == "update":
            if not validate_user_document_update(update_data):
                return jsonify({"response": "Invalid update format. Please use valid 'name', 'age', or 'city' fields."})
            try:
                result = users_collection.update_one(filter_data, {"$set": update_data})
            except Exception as e:
                return jsonify({"response": f"MongoDB error: {str(e)}"})
            log_action("update", {"filter": filter_data, "update": update_data})

            message_history.append({"role": "assistant", "content": ai_raw})
            sessions_collection.update_one(
                {"session_id": session_id},
                {"$set": {"messages": message_history, "last_updated": datetime.utcnow()}},
                upsert=True
            )

            return jsonify({"response": f"{result.modified_count} document(s) updated."})

        # ✅ Handle DELETE
        elif action == "delete":
            try:
                result = users_collection.delete_one(filter_data)
            except Exception as e:
                return jsonify({"response": f"MongoDB error: {str(e)}"})
            log_action("delete", {"filter": filter_data})

            message_history.append({"role": "assistant", "content": ai_raw})
            sessions_collection.update_one(
                {"session_id": session_id},
                {"$set": {"messages": message_history, "last_updated": datetime.utcnow()}},
                upsert=True
            )

            return jsonify({"response": f"{result.deleted_count} document(s) deleted."})

        # ✅ Handle INSERT
        elif action == "insert":
            if "birth_year" in new_doc:
                try:
                    birth_year = int(new_doc["birth_year"])
                    new_doc["age"] = datetime.utcnow().year - birth_year
                    del new_doc["birth_year"]
                except Exception:
                    return jsonify({"response": "Invalid birth_year"})

            if not validate_user_document_insert(new_doc):
                return jsonify({"response": "Invalid document format. Must include name (str), age (int), city (str)."})
            try:
                users_collection.insert_one(new_doc)
            except Exception as e:
                return jsonify({"response": f"MongoDB error: {str(e)}"})
            log_action("insert", {"document": new_doc})

            message_history.append({"role": "assistant", "content": ai_raw})
            sessions_collection.update_one(
                {"session_id": session_id},
                {"$set": {"messages": message_history, "last_updated": datetime.utcnow()}},
                upsert=True
            )

            return jsonify({"response": "Document inserted successfully."})

        else:
            return jsonify({"response": "Unsupported user action."})

    except Exception as e:
        return jsonify({"response": f"Something went wrong: {str(e)}"})

if __name__ == "__main__":
    app.run(
        debug=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )