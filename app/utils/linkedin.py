# app/utils/linkedin.py
import os
import requests
import json
from datetime import datetime, timedelta, time
from app.utils.db_utils import get_db

DATASET_ID = "gd_l1viktl72bvl7bjuj0"
SCRAPE_URL = (
    f"https://api.brightdata.com/datasets/v3/scrape"
    f"?dataset_id={DATASET_ID}&notify=false&include_errors=true"
)

CACHE_HOURS = 24

def fetch_linkedin_profile_brightdata(linkedin_url: str, user_id: str, force_refresh: bool = False) -> dict:
    db = get_db()
    coll = db.linkedin_data

    # === 1. Check cache ===
    cached = coll.find_one({"user_id": user_id})
    if cached and not force_refresh:
        last_updated = cached.get("last_updated")
        if last_updated:
            age_hours = (datetime.utcnow() - last_updated).total_seconds() / 3600
            if age_hours < CACHE_HOURS:
                print(f"[LinkedIn] CACHE HIT: Using {len(cached)} fields (age: {age_hours:.1f}h)")
                return {"status": "success", "message": "From cache"}

    # === 2. Fetch with retry (2 attempts) ===
    api_key = os.getenv("LINKEDIN_API_KEY")
    if not api_key:
        return {"status": "error", "message": "API key missing"}

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"input": [{"url": linkedin_url}]}

    for attempt in range(2):
        try:
            print(f"[LinkedIn] Attempt {attempt + 1}: Fetching {linkedin_url}")
            response = requests.post(SCRAPE_URL, headers=headers, json=payload, timeout=90)  # 90s
            print(f"[LinkedIn] HTTP {response.status_code}")

            if response.status_code != 200:
                error = response.json().get("error", "Unknown")
                print(f"[LinkedIn] API error: {error}")
                if attempt == 1:
                    break
                continue

            data = response.json()
            profile_data = data if isinstance(data, dict) and "id" in data else data[0] if isinstance(data, list) and data else None

            if not profile_data:
                print(f"[LinkedIn] No data in response")
                if attempt == 1:
                    break
                continue

            # === 3. Save ===
            profile_data["user_id"] = user_id
            profile_data["input_url"] = linkedin_url
            profile_data["last_updated"] = datetime.utcnow()

            coll.update_one({"user_id": user_id}, {"$set": profile_data}, upsert=True)
            print(f"[LinkedIn] SUCCESS: Saved {len(profile_data)} fields")
            return {"status": "success", "message": "Fetched & cached"}

        except requests.exceptions.Timeout:
            print(f"[LinkedIn] Timeout on attempt {attempt + 1}")
            if attempt == 1:
                break
            time.sleep(5)
        except Exception as e:
            print(f"[LinkedIn] Error: {e}")
            if attempt == 1:
                break

    # === 4. Fallback to cache if exists ===
    if cached:
        print(f"[LinkedIn] FALLBACK: Using stale cache")
        return {"status": "success", "message": "Using cached data"}
    
    return {"status": "error", "message": "Failed after 2 attempts"}