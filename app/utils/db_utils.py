from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv, find_dotenv
import datetime
from bson import ObjectId
import bcrypt
import sys

dotenv_path = find_dotenv()

if dotenv_path:
    load_dotenv(dotenv_path)
else:
    print(
        "Warning: .env file not found with find_dotenv(); make sure env vars are set.",
        file=sys.stderr
    )

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME_RAW = os.getenv("DB_NAME", "catalyst_ai_db")

DB_NAME = DB_NAME_RAW.strip().replace(" ", "_")


if not MONGO_URI:
    raise RuntimeError(
        "❌ MONGO_URI is not set in environment.\n"
        "You must add it in your .env file.\n\n"
    )


try:
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    client.server_info()

except Exception as e:
    raise RuntimeError(
        f"❌ Failed to connect to MongoDB.\n"
        f"Error: {e}\n\n"
        "Common fixes:\n"
        "1) Ensure DB name is included in your URI.\n"
        "2) Check username/password.\n"
        "3) Ensure IP whitelisted in MongoDB Atlas.\n"
        "4) Install dnspython: pip install dnspython.\n"
        "5) Check DNS / try hotspot.\n"
    ) from e

db = client[DB_NAME]

def check_existing_user(email, username):
    return db.users.find_one({
        "$or": [
            {"email": email.lower()},
            {"user_id": username.lower()}
        ]
    })


def insert_user(user_data):
    return db.users.insert_one(user_data)

def find_user_by_credentials(email_or_user_id):
    return db.users.find_one({
        "$or": [
            {"email": email_or_user_id},
            {"user_id": email_or_user_id}
        ]
    })


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(provided_password, stored_password):
    return bcrypt.checkpw(provided_password.encode(), stored_password.encode())


def get_user_by_id(user_id):
    return db.users.find_one({"user_id": user_id})


def update_user_profile(user_id, update_data):
    return db.users.update_one(
        {"user_id": user_id},
        {"$set": update_data}
    )

def get_user_roadmap(user_id):
    user = get_user_by_id(user_id)
    return user.get("road_map") if user and "road_map" in user else None


def update_learning_plan(user_id, phase_id, learning_plan):
    return db.users.update_one(
        {"user_id": user_id, "active_modules.phase_id": phase_id},
        {"$set": {"active_modules.$.learning_plan": learning_plan}}
    )


def add_module_to_user(user_id, module_data):
    return db.users.update_one(
        {"user_id": user_id},
        {"$addToSet": {"active_modules": module_data}}
    )


def update_task_completion(user_id, phase_id, week_num, day_num, completed, completion_date=None):
    if completion_date is None:
        completion_date = datetime.datetime.now() if completed else None

    return db.users.update_one(
        {
            "user_id": user_id,
            "active_modules.phase_id": phase_id,
        },
        {
            "$set": {
                "active_modules.$.learning_plan.weekly_schedule.$[week].daily_tasks.$[day].completed": completed,
                "active_modules.$.learning_plan.weekly_schedule.$[week].daily_tasks.$[day].completed_date": completion_date
            }
        },
        array_filters=[
            {"week.week": int(week_num)},
            {"day.day": int(day_num)}
        ]
    )

def add_notification(notification_data):
    return db.notifications.insert_one(notification_data)


def get_user_notifications(user_id, limit=5, unread_only=True):
    query = {"user_id": user_id}
    if unread_only:
        query["read"] = False
    return list(db.notifications.find(query).sort("created_at", -1).limit(limit))


def mark_notification_read(notification_id):
    return db.notifications.update_one(
        {"_id": ObjectId(notification_id)},
        {"$set": {"read": True}}
    )