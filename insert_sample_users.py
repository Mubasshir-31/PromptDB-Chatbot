from mongodb_utils import users_collection, log_action

# ✅ Update and Delete operations (only)
operations = [
    # 🔁 Updates
    {"type": "update", "filter": {"name": "Sneha", "city": "Pune"}, "update": {"city": "Nagpur"}},
    {"type": "update", "filter": {"name": "Neha"}, "update": {"age": 30}},
    {"type": "update", "filter": {"name": "Amit"}, "update": {"city": "Thane"}},
    {"type": "update", "filter": {"name": "Divya"}, "update": {"age": 29}},
    {"type": "update", "filter": {"name": "Gaurav"}, "update": {"city": "Surat"}},
    {"type": "update", "filter": {"name": "Alok"}, "update": {"age": 28}},
    {"type": "update", "filter": {"name": "Priya"}, "update": {"age": 31}},

    # ❌ Deletes
    {"type": "delete", "filter": {"name": "Kunal"}},
    {"type": "delete", "filter": {"name": "Aakash"}},
    {"type": "delete", "filter": {"name": "Harsh"}},
]

# 🔄 Execute all operations
for op in operations:
    if op["type"] == "update":
        result = users_collection.update_one(op["filter"], {"$set": op["update"]})
        if result.modified_count > 0:
            log_action("update", {"filter": op["filter"], "update": op["update"]})
            print(f"✅ Updated: {op['filter']} with {op['update']}")
        else:
            print(f"⚠️ No match for update: {op['filter']}")
    elif op["type"] == "delete":
        result = users_collection.delete_one(op["filter"])
        if result.deleted_count > 0:
            log_action("delete", {"filter": op["filter"]})
            print(f"🗑️ Deleted: {op['filter']}")
        else:
            print(f"⚠️ No match for delete: {op['filter']}")

print("✅ All updates and deletes completed.")
