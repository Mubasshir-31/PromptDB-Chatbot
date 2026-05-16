from mongodb_utils import get_collections, log_action


operations = [
    {"type": "update", "filter": {"name": "Sneha", "city": "Pune"}, "update": {"city": "Nagpur"}},
    {"type": "update", "filter": {"name": "Neha"}, "update": {"age": 30}},
    {"type": "update", "filter": {"name": "Amit"}, "update": {"city": "Thane"}},
    {"type": "update", "filter": {"name": "Divya"}, "update": {"age": 29}},
    {"type": "update", "filter": {"name": "Gaurav"}, "update": {"city": "Surat"}},
    {"type": "update", "filter": {"name": "Alok"}, "update": {"age": 28}},
    {"type": "update", "filter": {"name": "Priya"}, "update": {"age": 31}},
    {"type": "delete", "filter": {"name": "Kunal"}},
    {"type": "delete", "filter": {"name": "Aakash"}},
    {"type": "delete", "filter": {"name": "Harsh"}},
]


def main():
    users_collection, _, _ = get_collections()

    for op in operations:
        if op["type"] == "update":
            result = users_collection.update_one(op["filter"], {"$set": op["update"]})
            if result.modified_count > 0:
                log_action("update", {"filter": op["filter"], "update": op["update"]})
                print(f"Updated: {op['filter']} with {op['update']}")
            else:
                print(f"No match for update: {op['filter']}")
        elif op["type"] == "delete":
            result = users_collection.delete_one(op["filter"])
            if result.deleted_count > 0:
                log_action("delete", {"filter": op["filter"]})
                print(f"Deleted: {op['filter']}")
            else:
                print(f"No match for delete: {op['filter']}")

    print("All updates and deletes completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"MongoDB connection failed. Check MONGO_URI in .env and your DNS/network. Details: {e}")
