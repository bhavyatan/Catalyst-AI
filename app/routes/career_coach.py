from flask import Blueprint, render_template, request, redirect, url_for, session
from datetime import datetime
from markdown2 import Markdown
from app.utils.llm_utils import get_mistral_response, fetch_github_projects
from app.utils.db_utils import get_db, get_user_by_id
from app.utils.linkedin import fetch_linkedin_profile_brightdata

# Initialize markdown converter
markdowner = Markdown()

# Career coach blueprint
career_coach_bp = Blueprint('career_coach_bp', __name__)

def generate_prompt(user_data, user_query, chat_history):
    # === EXTRACT NAME SAFELY ===
    first_name = user_data.get("first_name", "User").split()[0]
    address_name = first_name if first_name and first_name != "User" else "there"

    headline = user_data.get("position", "Student")
    skills = user_data.get("skills", [])
    skills_str = ', '.join(skills) if skills else 'None'

    experience = user_data.get("experience", [])[:2]
    exp_str = ', '.join([
        f"{e.get('title','Role')} at {e.get('company','Company')}"
        for e in experience
    ]) if experience else 'None'

    # === CHAT HISTORY (last 2) ===
    recent = chat_history[-2:]
    history_str = "\n".join([
        f"User: {m.get('prompt','')}\nLeo: {m.get('raw_response','')}"
        for m in recent if isinstance(m, dict)
    ]) or "First message."

    # === FINAL PROMPT: GIVE NAME TO MISTRAL ===
    return f"""
        You are Leo, a friendly career coach.

        User Profile:
        - Name: {first_name}
        - Current Role: {headline}
        - Skills: {skills_str}
        - Recent Experience: {exp_str}

        Chat History:
        {history_str}

        User Question: "{user_query}"

        Instructions:
        - Address the user by name: "{address_name}"
        - Start with "Hi {address_name}," or similar
        - Give 1 actionable tip
        - Keep under 2 short paragraphs
        - Be warm, concise, and professional
        """.strip()

@career_coach_bp.route('/your-career_coach-leo011', methods=['POST', 'GET'])
def career_coach():
    if "user_id" not in session:
        return redirect(url_for("auth_bp.sign_in"))

    db = get_db()
    leo_chat_history = db.career_coach
    linkedin_coll = db.linkedin_data

    if request.method == 'POST':
        user_id = session['user_id']
        user_query = request.form['userQuery']

        # --------------------------------------------------------------
        # 1. Get basic user data
        # --------------------------------------------------------------
        user_record = get_user_by_id(user_id)
        linkedin_url = user_record.get('linkedinProfile')
        
        # Try to fetch LinkedIn (non-blocking)
        if linkedin_url:
            try:
                fetch_linkedin_profile_brightdata(linkedin_url, user_id)
            except Exception as e:
                print(f"[Leo] LinkedIn fetch failed: {e}")

        # --------------------------------------------------------------
        # 2. Load data (LinkedIn OR fallback)
        # --------------------------------------------------------------
        user_data = linkedin_coll.find_one({"user_id": user_id})
        if not user_data:
            user_data = user_record or {}
            user_data["position"] = "Student"
            user_data["skills"] = []
            user_data["experience"] = []
            user_data["education"] = []
            user_data["about"] = "No summary"

        # Extract first name for greeting
        first_name = user_data.get("first_name", user_record.get("name", "there")).split()[0]
        address_name = first_name if first_name and first_name != "User" else "there"

        # --------------------------------------------------------------
        # 3. Chat history
        # --------------------------------------------------------------
        conv = leo_chat_history.find_one({"user_id": user_id})
        chat_history = conv.get("messages", []) if conv else []

        # --------------------------------------------------------------
        # 4. Generate response
        # --------------------------------------------------------------
        try:
            prompt = generate_prompt(user_data, user_query, chat_history)
            raw_resp = get_mistral_response(prompt, tokens=300)

            # Let Mistral handle name naturally
            html_resp = markdowner.convert(raw_resp)
        except Exception as e:
            print(f"[Leo] Error: {e}")
            first_name = user_data.get("first_name", "there").split()[0]
            raw_resp = f"{first_name}, I'm here to help!"
            html_resp = markdowner.convert(raw_resp)

        # --------------------------------------------------------------
        # 5. Persist conversation
        # --------------------------------------------------------------
        new_msg = {
            "prompt": user_query,
            "response": html_resp,
            "raw_response": raw_resp,
            "time": datetime.utcnow(),
        }

        if not conv:
            conv_id = f"conv_{int(datetime.now().timestamp())}"
            leo_chat_history.insert_one({
                "user_id": user_id,
                "conversation_id": conv_id,
                "messages": [new_msg],
            })
            messages = [new_msg]
        else:
            messages = conv["messages"] + [new_msg]
            messages = [{
                "prompt": m["prompt"],
                "response": m.get("response", markdowner.convert(m.get("raw_response", ""))),
                "time": m["time"]
            } for m in messages]

            leo_chat_history.update_one(
                {"user_id": user_id},
                {"$set": {"messages": messages}}
            )

        return render_template("career_coach.html", messages=messages)

    # GET route
    conv = leo_chat_history.find_one({"user_id": session["user_id"]})
    messages = []
    if conv:
        messages = [{
            "prompt": m["prompt"],
            "response": m.get("response", markdowner.convert(m.get("raw_response", ""))),
            "time": m["time"]
        } for m in conv.get("messages", [])]

    return render_template("career_coach.html", messages=messages)