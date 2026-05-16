from datetime import UTC, datetime
from functools import wraps
import csv
import io
import json
import os

from bson import ObjectId
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from openai import OpenAI
from pymongo import MongoClient


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")

openai_client = None
mongo_client = None


def now_utc():
    return datetime.now(UTC)


def serialize_doc(doc):
    if isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, datetime):
        return doc.isoformat()
    if not isinstance(doc, dict):
        return doc

    clean = {}
    for key, value in doc.items():
        clean[key] = serialize_doc(value)
    return clean


def wants_json():
    return request.path.startswith("/api/") or request.path == "/chat"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("authenticated"):
            return view(*args, **kwargs)
        if wants_json():
            return jsonify({"error": "Authentication required."}), 401
        return redirect(url_for("login", next=request.path))

    return wrapped


def get_openai_client():
    global openai_client

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is missing in .env.")

    if openai_client is None:
        openai_client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    return openai_client


def get_mongo_collections():
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

    db = mongo_client["PromptDB_Database"]
    return db["sessions"], db["users"], db["logs"]


def get_mongo_status():
    try:
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            return {"ok": False, "label": "Not configured", "detail": "MONGO_URI is missing in .env."}

        if mongo_client is None:
            get_mongo_collections()

        mongo_client.admin.command("ping")
        return {"ok": True, "label": "Connected", "detail": "MongoDB responded to ping."}
    except Exception as e:
        return {"ok": False, "label": "Unavailable", "detail": str(e)}


def validate_user_document_insert(doc):
    if not isinstance(doc, dict):
        return False

    required_fields = {"name": str, "age": int, "city": str}
    for field, expected_type in required_fields.items():
        if field not in doc or not isinstance(doc[field], expected_type):
            return False

    return True


def validate_user_document_update(doc):
    if not isinstance(doc, dict) or not doc:
        return False

    allowed_fields = {"name": str, "age": int, "city": str}
    for field, value in doc.items():
        if field not in allowed_fields or not isinstance(value, allowed_fields[field]):
            return False

    return True


def is_valid_filter(data):
    allowed_fields = {"name", "age", "city"}
    allowed_operators = {"$gt", "$lt", "$in", "$regex", "$options"}

    if isinstance(data, dict):
        for key, value in data.items():
            if key not in allowed_fields and key not in allowed_operators:
                return False
            if isinstance(value, dict) and not is_valid_filter(value):
                return False

    return True


def normalize_find_filter(filter_data):
    normalized = dict(filter_data or {})
    if "city" in normalized:
        city_val = normalized["city"]
        if isinstance(city_val, str):
            normalized["city"] = {"$regex": f"^{city_val}$", "$options": "i"}
        elif isinstance(city_val, dict) and "$in" in city_val:
            normalized["city"]["$in"] = [c.strip() for c in city_val["$in"]]
    return normalized


def parse_local_command(message):
    text = message.strip()
    lowered = text.lower()

    if lowered.startswith(("show", "find", "list")):
        command = {"action": "find", "collection": "users", "filter": {}}

        if "last" in lowered:
            words = lowered.split()
            for index, word in enumerate(words):
                if word == "last" and index + 1 < len(words) and words[index + 1].isdigit():
                    command["sort"] = {"_id": -1}
                    command["limit"] = int(words[index + 1])
                    break

        if "youngest" in lowered:
            command["sort"] = {"age": 1}
        elif "oldest" in lowered:
            command["sort"] = {"age": -1}
            command["limit"] = 1

        if " from " in lowered:
            city = text[lowered.rfind(" from ") + 6:].strip(" .")
            if city:
                command["filter"]["city"] = city
        elif " in " in lowered:
            city = text[lowered.rfind(" in ") + 4:].strip(" .")
            if city:
                command["filter"]["city"] = city

        return command

    if lowered.startswith(("add ", "insert ")):
        working = text
        for prefix in ("add ", "insert "):
            if lowered.startswith(prefix):
                working = text[len(prefix):]
                break

        parts = [part.strip(" .") for part in working.split(",")]
        if len(parts) >= 3:
            name = parts[0].strip()
            age = None
            city = None

            for part in parts[1:]:
                part_lower = part.lower()
                if "age" in part_lower:
                    digits = "".join(ch for ch in part if ch.isdigit())
                    if digits:
                        age = int(digits)
                if "from " in part_lower:
                    city = part[part_lower.rfind("from ") + 5:].strip()

            if name and age is not None and city:
                return {
                    "action": "insert",
                    "collection": "users",
                    "document": {"name": name, "age": age, "city": city},
                }

    if lowered.startswith("update "):
        name = text.split()[1].strip("'s, ")
        digits = "".join(ch for ch in text if ch.isdigit())
        if name and digits and "age" in lowered:
            return {
                "action": "update",
                "collection": "users",
                "filter": {"name": name},
                "update": {"age": int(digits)},
            }

    if lowered.startswith("delete "):
        name = ""
        if "named " in lowered:
            name = text[lowered.rfind("named ") + 6:].strip(" .")
        elif "name " in lowered:
            name = text[lowered.rfind("name ") + 5:].strip(" .")
        elif "user " in lowered:
            name = text[lowered.rfind("user ") + 5:].strip(" .")

        if name:
            return {"action": "delete", "collection": "users", "filter": {"name": name}}

    return None


def command_requires_confirmation(command):
    return command.get("action") in {"insert", "update", "delete"}


def validate_command(command):
    if not isinstance(command, dict):
        return "Command must be a JSON object."

    action = command.get("action")
    collection = command.get("collection")
    filter_data = command.get("filter", {})
    update_data = command.get("update", {})
    new_doc = command.get("document", {})

    if collection != "users":
        return "Only the users collection is supported."
    if action not in {"find", "insert", "update", "delete"}:
        return "Unsupported action."
    if not is_valid_filter(filter_data):
        return "Invalid filter. Only name, age, city, and allowed operators are permitted."
    if action == "insert":
        if "birth_year" in new_doc:
            try:
                birth_year = int(new_doc["birth_year"])
                new_doc["age"] = now_utc().year - birth_year
                del new_doc["birth_year"]
            except Exception:
                return "Invalid birth_year."
        if not validate_user_document_insert(new_doc):
            return "Invalid document. Include name (str), age (int), and city (str)."
    if action == "update" and not validate_user_document_update(update_data):
        return "Invalid update. Use valid name, age, or city fields."

    return None


def generate_command(user_message, message_history):
    local_command = parse_local_command(user_message)
    if local_command is not None:
        return local_command, "local"

    system_prompt = {
        "role": "system",
        "content": (
            "You are a JSON command generator for MongoDB operations. "
            "Return one valid JSON object only. Required keys: action, collection. "
            "Supported actions: find, insert, update, delete. Supported collection: users. "
            "Supported fields: name, age, city. Optional keys: filter, update, document, sort, limit. "
            "Do not use aggregation or natural language."
        ),
    }
    response = get_openai_client().chat.completions.create(
        model=os.getenv("OPENROUTER_MODEL", "openrouter/free"),
        messages=[system_prompt] + message_history[-5:],
    )
    ai_raw = response.choices[0].message.content.strip()
    fixed_text = ai_raw.replace("'", '"').replace("“", '"').replace("”", '"')
    return json.loads(fixed_text), "ai"


def save_session_history(sessions_collection, session_id, message_history):
    sessions_collection.update_one(
        {"session_id": session_id},
        {"$set": {"messages": message_history, "last_updated": now_utc()}},
        upsert=True,
    )


def write_audit(logs_collection, *, action, prompt, command, status, result_summary, parser="unknown", before=None, after=None):
    logs_collection.insert_one({
        "timestamp": now_utc(),
        "actor": session.get("username", "anonymous"),
        "action": action,
        "prompt": prompt,
        "command": command,
        "status": status,
        "result_summary": result_summary,
        "parser": parser,
        "before": before,
        "after": after,
    })


def execute_command(command, users_collection):
    action = command.get("action")
    filter_data = command.get("filter", {})

    if action == "find":
        query = normalize_find_filter(filter_data)
        cursor = users_collection.find(query, {"_id": 0})
        if command.get("sort"):
            field, direction = list(command["sort"].items())[0]
            cursor = cursor.sort(field, direction)
        if command.get("limit"):
            cursor = cursor.limit(int(command["limit"]))
        results = list(cursor)
        return {
            "response": results if results else "No matching records found.",
            "summary": f"{len(results)} document(s) found.",
        }

    if action == "insert":
        document = dict(command.get("document", {}))
        result = users_collection.insert_one(document)
        return {
            "response": "Document inserted successfully.",
            "summary": "1 document inserted.",
            "after": serialize_doc(users_collection.find_one({"_id": result.inserted_id}) or {}),
        }

    if action == "update":
        before = [serialize_doc(doc) for doc in users_collection.find(filter_data)]
        result = users_collection.update_one(filter_data, {"$set": command.get("update", {})})
        after = [serialize_doc(doc) for doc in users_collection.find(filter_data)]
        return {
            "response": f"{result.modified_count} document(s) updated.",
            "summary": f"{result.modified_count} document(s) updated.",
            "before": before,
            "after": after,
        }

    if action == "delete":
        before = users_collection.find_one(filter_data)
        result = users_collection.delete_one(filter_data)
        return {
            "response": f"{result.deleted_count} document(s) deleted.",
            "summary": f"{result.deleted_count} document(s) deleted.",
            "before": serialize_doc(before) if before else None,
        }

    return {"response": "Unsupported user action.", "summary": "Unsupported action."}


def database_error_response(error):
    return jsonify({
        "response": (
            "Database connection failed. Check MONGO_URI in .env and your DNS/network. "
            f"Details: {error}"
        )
    })


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        expected_user = os.getenv("ADMIN_USERNAME", "PromptDB")
        expected_password = os.getenv("ADMIN_PASSWORD", "PromptDatabase")

        if username == expected_user and password == expected_password:
            session["authenticated"] = True
            session["username"] = username
            return redirect(request.args.get("next") or url_for("home"))

        return render_template("login.html", error="Invalid username or password.")

    return render_template("login.html", error="")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def home():
    return render_template("index.html")


@app.route("/users")
@login_required
def users_page():
    return render_template("users.html")


@app.route("/logs")
@login_required
def logs_page():
    return render_template("logs.html")


@app.route("/about")
@login_required
def about():
    return render_template("about.html")


@app.route("/features")
@login_required
def features():
    return render_template("features.html")


@app.route("/contact")
@login_required
def contact():
    return render_template("contact.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/status")
@login_required
def api_status():
    openrouter_configured = bool(os.getenv("OPENROUTER_API_KEY"))
    return jsonify({
        "app": {"ok": True, "label": "Running", "detail": "Flask server is online."},
        "mongo": get_mongo_status(),
        "openrouter": {
            "ok": openrouter_configured,
            "label": "Configured" if openrouter_configured else "Missing key",
            "detail": "OPENROUTER_API_KEY is present." if openrouter_configured else "OPENROUTER_API_KEY is missing.",
        },
    })


@app.route("/api/examples")
@login_required
def api_examples():
    return jsonify({
        "examples": [
            {"label": "Find users", "prompt": "Show users from Delhi", "operation": "find"},
            {"label": "Insert record", "prompt": "Add Raj, age 25, from Noida", "operation": "insert"},
            {"label": "Update field", "prompt": "Update Rahul age to 30", "operation": "update"},
            {"label": "Delete record", "prompt": "Delete user named Kunal", "operation": "delete"},
            {"label": "Sort results", "prompt": "Show the youngest users", "operation": "find"},
            {"label": "Limit results", "prompt": "Show the last 5 users", "operation": "find"},
        ],
        "schema": {
            "collection": "users",
            "fields": [
                {"name": "name", "type": "string", "required": True},
                {"name": "age", "type": "integer", "required": True},
                {"name": "city", "type": "string", "required": True},
            ],
            "allowed_actions": ["find", "insert", "update", "delete"],
        },
    })


@app.route("/api/session/<session_id>", methods=["DELETE"])
@login_required
def clear_session(session_id):
    try:
        sessions_collection, _, _ = get_mongo_collections()
        sessions_collection.delete_one({"session_id": session_id})
        return jsonify({"ok": True, "message": "Session cleared."})
    except Exception as e:
        return database_error_response(e)


@app.route("/api/preview", methods=["POST"])
@login_required
def preview_command():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not user_message:
        return jsonify({"error": "Please enter a message."}), 400

    try:
        sessions_collection, _, _ = get_mongo_collections()
        session_doc = sessions_collection.find_one({"session_id": session_id})
        message_history = session_doc["messages"] if session_doc else []
        command, parser = generate_command(user_message, message_history + [{"role": "user", "content": user_message}])
    except Exception as e:
        return jsonify({"error": f"Could not generate command: {e}"}), 400

    validation_error = validate_command(command)
    if validation_error:
        return jsonify({"error": validation_error, "command": command}), 400

    return jsonify({
        "command": command,
        "parser": parser,
        "requires_confirmation": command_requires_confirmation(command),
        "message": "Review this command before execution." if command_requires_confirmation(command) else "Safe read command ready.",
    })


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    confirmed = bool(data.get("confirmed"))
    command = data.get("command")
    parser = data.get("parser", "unknown")

    if not user_message:
        return jsonify({"response": "Please enter a message."})

    if user_message.lower() in {"hello", "hi", "hey"}:
        return jsonify({"response": "Hello! I am PromptDB, a database command generator. How can I help you?"})

    if len(user_message) > 500:
        return jsonify({"response": "Your message is too long. Please keep it under 500 characters."})

    try:
        sessions_collection, users_collection, logs_collection = get_mongo_collections()
        session_doc = sessions_collection.find_one({"session_id": session_id})
        message_history = session_doc["messages"] if session_doc else []

        if command is None:
            command, parser = generate_command(user_message, message_history + [{"role": "user", "content": user_message}])

        validation_error = validate_command(command)
        if validation_error:
            write_audit(
                logs_collection,
                action=command.get("action", "unknown") if isinstance(command, dict) else "unknown",
                prompt=user_message,
                command=command,
                status="rejected",
                result_summary=validation_error,
                parser=parser,
            )
            return jsonify({"response": validation_error})

        if command_requires_confirmation(command) and not confirmed:
            return jsonify({
                "requires_confirmation": True,
                "command": command,
                "parser": parser,
                "response": "Review and confirm this write operation before execution.",
            })

        result = execute_command(command, users_collection)
        message_history.append({"role": "user", "content": user_message})
        message_history.append({"role": "assistant", "content": json.dumps(command)})
        save_session_history(sessions_collection, session_id, message_history)
        write_audit(
            logs_collection,
            action=command.get("action", "unknown"),
            prompt=user_message,
            command=command,
            status="success",
            result_summary=result.get("summary", ""),
            parser=parser,
            before=result.get("before"),
            after=result.get("after"),
        )
        return jsonify({
            "response": result.get("response"),
            "command": command,
            "parser": parser,
            "summary": result.get("summary"),
        })
    except Exception as e:
        try:
            _, _, logs_collection = get_mongo_collections()
            write_audit(
                logs_collection,
                action=command.get("action", "unknown") if isinstance(command, dict) else "unknown",
                prompt=user_message,
                command=command,
                status="failed",
                result_summary=str(e),
                parser=parser,
            )
        except Exception:
            pass
        return jsonify({"response": f"Something went wrong: {e}"})


@app.route("/api/users", methods=["GET", "POST"])
@login_required
def api_users():
    _, users_collection, logs_collection = get_mongo_collections()

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        doc = {
            "name": data.get("name", "").strip(),
            "age": int(data.get("age", 0)),
            "city": data.get("city", "").strip(),
        }
        if not validate_user_document_insert(doc):
            return jsonify({"error": "Invalid user document."}), 400

        inserted = users_collection.insert_one(doc)
        created = serialize_doc(users_collection.find_one({"_id": inserted.inserted_id}) or {})
        write_audit(
            logs_collection,
            action="insert",
            prompt="Manual dashboard create",
            command={"action": "insert", "collection": "users", "document": doc},
            status="success",
            result_summary="1 document inserted from dashboard.",
            parser="dashboard",
            after=created,
        )
        return jsonify({"user": created}), 201

    query = request.args.get("q", "").strip()
    sort_field = request.args.get("sort", "name")
    sort_dir = -1 if request.args.get("dir") == "desc" else 1
    allowed_sort = {"name", "age", "city", "_id"}
    if sort_field not in allowed_sort:
        sort_field = "name"

    filter_data = {}
    if query:
        filter_data = {"$or": []}
        # Keep dashboard search explicit and safe without passing $or through chat validation.
        filter_data["$or"].append({"name": {"$regex": query, "$options": "i"}})
        filter_data["$or"].append({"city": {"$regex": query, "$options": "i"}})

    users = [serialize_doc(doc) for doc in users_collection.find(filter_data).sort(sort_field, sort_dir).limit(200)]
    return jsonify({"users": users})


@app.route("/api/users/<user_id>", methods=["PATCH", "DELETE"])
@login_required
def api_user_detail(user_id):
    _, users_collection, logs_collection = get_mongo_collections()

    try:
        object_id = ObjectId(user_id)
    except Exception:
        return jsonify({"error": "Invalid user id."}), 400

    if request.method == "DELETE":
        before = users_collection.find_one({"_id": object_id})
        result = users_collection.delete_one({"_id": object_id})
        write_audit(
            logs_collection,
            action="delete",
            prompt="Manual dashboard delete",
            command={"action": "delete", "collection": "users", "filter": {"_id": user_id}},
            status="success",
            result_summary=f"{result.deleted_count} document(s) deleted from dashboard.",
            parser="dashboard",
            before=serialize_doc(before) if before else None,
        )
        return jsonify({"deleted": result.deleted_count})

    data = request.get_json(silent=True) or {}
    update = {}
    for field in ("name", "city"):
        if field in data:
            update[field] = str(data[field]).strip()
    if "age" in data:
        update["age"] = int(data["age"])
    if not validate_user_document_update(update):
        return jsonify({"error": "Invalid update document."}), 400

    before = users_collection.find_one({"_id": object_id})
    result = users_collection.update_one({"_id": object_id}, {"$set": update})
    after = users_collection.find_one({"_id": object_id})
    write_audit(
        logs_collection,
        action="update",
        prompt="Manual dashboard update",
        command={"action": "update", "collection": "users", "filter": {"_id": user_id}, "update": update},
        status="success",
        result_summary=f"{result.modified_count} document(s) updated from dashboard.",
        parser="dashboard",
        before=serialize_doc(before) if before else None,
        after=serialize_doc(after) if after else None,
    )
    return jsonify({"user": serialize_doc(after) if after else None})


@app.route("/api/logs")
@login_required
def api_logs():
    _, _, logs_collection = get_mongo_collections()
    logs = [
        serialize_doc(doc)
        for doc in logs_collection.find({}).sort("timestamp", -1).limit(100)
    ]
    return jsonify({"logs": logs})


@app.route("/api/export/users.<file_type>")
@login_required
def export_users(file_type):
    _, users_collection, _ = get_mongo_collections()
    users = [serialize_doc(doc) for doc in users_collection.find({}).sort("name", 1)]

    if file_type == "json":
        return jsonify({"users": users})

    if file_type == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["_id", "name", "age", "city"])
        writer.writeheader()
        for user in users:
            writer.writerow({
                "_id": user.get("_id", ""),
                "name": user.get("name", ""),
                "age": user.get("age", ""),
                "city": user.get("city", ""),
            })
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=promptdb_users.csv"},
        )

    return jsonify({"error": "Unsupported export type."}), 400


if __name__ == "__main__":
    app.run(
        debug=True,
        use_reloader=False,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
    )
