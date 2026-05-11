from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
import json
from dotenv import load_dotenv
from openai import OpenAI
import os
from datetime import datetime
import asyncio
import re

app = FastAPI()

# טעינת משתני סביבה
load_dotenv()

openai_api_key = os.getenv("OPENAI_API")
if not openai_api_key:
    print("WARNING: OPENAI_API environment variable is not set!")
    openai_api_key = "MISSING_KEY"

client = OpenAI(
    api_key=openai_api_key,
    base_url="https://api.groq.com/openai/v1"
)

# ניהול לוג
CHAT_LOG_FILE = "logs/chat_history.txt"
if not os.path.exists("logs"):
    os.makedirs("logs")
with open(CHAT_LOG_FILE, "w", encoding="utf-8") as f:
    f.write("")

# ניהול חיבורים
rooms = {} # {room_name: {username: websocket}}
user_to_room = {} # {username: room_name}
user_relationships = {} # {parent_username: child_username}
whisper_sessions = {}

# === רשימות אלגוריתמיות לסינון ===

OFFENSIVE_KEYWORDS = [
    "מטומטם", "טיפש", "סתום", "אפס", "מכוער", "דפוק", "זבל", "חרא", "כלב", 
    "idiot", "stupid", "dumb", "shut up", "ugly", "loser", "hate you"
]

def check_if_math(text: str) -> bool:
    """
    בודק האם הטקסט מכיל תבניות מתמטיות מובהקות.
    """
    math_patterns = [
        r"sqrt\(",          
        r"[a-zA-Z0-9]+\^",  
        r"[a-zA-Z0-9]+\s*=\s*", 
        r"[\d\w]+\s*[\+\-\*\/]\s*[\d\w]+", 
        r"\(.*\)\s*\/"      
    ]
    
    for pattern in math_patterns:
        if re.search(pattern, text):
            return True
    return False

def check_offensive_words(text: str) -> bool:
    clean_text = text.lower()
    for word in OFFENSIVE_KEYWORDS:
        if word in clean_text:
            return True
    return False

# ==========================================

class ConnectionManager:
    async def connect(self, websocket: WebSocket, username: str, room_name: str, parent_of: str = None):
        await websocket.accept()
        
        if room_name not in rooms:
            rooms[room_name] = {}
        
        rooms[room_name][username] = websocket
        user_to_room[username] = room_name
        
        if parent_of:
            user_relationships[username] = parent_of
            
        role = "Parent" if parent_of else "User"
        await self.broadcast(json.dumps({
            "type": "message", 
            "content": f"{username} ({role}) has joined the group: {room_name}"
        }), room_name)
        await self.send_user_list(room_name)
    
    async def disconnect(self, username: str):
        room_name = user_to_room.get(username)
        if room_name and room_name in rooms:
            if username in rooms[room_name]:
                del rooms[room_name][username]
            if not rooms[room_name]:
                del rooms[room_name]
        
        if username in user_to_room:
            del user_to_room[username]
        if username in user_relationships:
            del user_relationships[username]
        if username in whisper_sessions:
            del whisper_sessions[username]
            
        if room_name:
            await self.broadcast(json.dumps({
                "type": "message", 
                "content": f"{username} has left the group"
            }), room_name)
            await self.send_user_list(room_name)
    
    async def send_personal_message(self, message_json: dict, username: str):
        room_name = user_to_room.get(username)
        if room_name and room_name in rooms and username in rooms[room_name]:
            await rooms[room_name][username].send_text(json.dumps(message_json))
    
    async def broadcast(self, message: str, room_name: str):
        if room_name in rooms:
            for connection in rooms[room_name].values():
                await connection.send_text(message)
            
    async def send_user_list(self, room_name: str):
        if room_name in rooms:
            users_list = list(rooms[room_name].keys())
            msg = json.dumps({"type": "users", "users": users_list})
            for connection in rooms[room_name].values():
                await connection.send_text(msg)

    async def distribute_suggestions(self, suggestions: list, room_name: str, exclude_user: str):
        if room_name not in rooms:
            return
            
        recipients = [(u, c) for u, c in rooms[room_name].items() if u != exclude_user]
        
        if not recipients or not suggestions:
            return

        for i, (username, connection) in enumerate(recipients):
            suggestion_data = suggestions[i % len(suggestions)]
            insight = suggestion_data.get('insight', 'I noticed this.')
            response_text = suggestion_data.get('response_text', '')

            formatted_message = f"{insight} Maybe try saying: \"{response_text}\"" if response_text else insight
            
            msg = {
                "type": "ai_suggestion",
                "content": formatted_message,
                "for_message_by": exclude_user
            }
            await connection.send_text(json.dumps(msg))

manager = ConnectionManager()

# --- נתיבים ---

@app.get("/")
async def get():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "index.html")
    if not os.path.exists(file_path):
         file_path = "index.html"
    with open(file_path, encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

# --- לוגיקה היברידית: אלגוריתם + AI ---
async def analyze_chat_event(sender_username: str, message_content: str, room_name: str):
    try:
        with open(CHAT_LOG_FILE, "r", encoding="utf-8") as f:
            history = f.read()[-3000:] 
    except:
        history = ""

    # === שלב 1: בדיקה אלגוריתמית ===
    is_bullying = False
    ai_context_instruction = ""

    if check_if_math(message_content):
        is_bullying = False
        ai_context_instruction = "Educational message detected (math/code). Treat this as study help."
    
    elif check_offensive_words(message_content):
        is_bullying = True
        ai_context_instruction = "Explicit offensive word detected. This is cyberbullying."

    else:
        is_bullying = False 
        ai_context_instruction = "Check if this message contains subtle bullying, harassment, or social exclusion that the algorithm might have missed."

    # === שלב 2: שימוש ב-AI ליצירת תובנות והצעות ===
    
    system_prompt = (
        "You are an invisible observer analyzing a chat between students. DO NOT assume messages are directed at you.\n"
        f"Bullying status: {is_bullying}.\n"
        f"Context: {ai_context_instruction}\n\n"
        "Your task is to return a JSON containing: \n"
        "1. 'suggestions': An array of 3 objects, each with 'insight' and 'response_text', intended to help the RECIPIENT of the message.\n"
        "   - 'insight': A short, 1-sentence empathetic thought validating how the recipient might feel about the sender's specific message (e.g., 'It hurts when someone says that.'). Do NOT speak about yourself.\n"
        "   - 'response_text': A practical, natural, and authentic way the recipient could reply to the sender.\n"
        "2. 'is_bullying': (Boolean) true if you detect harmful, offensive, violent, or exclusionary behavior.\n"
        "3. 'parent_alert_text': (Optional) If is_bullying is true, write a highly specific, practical 1-2 sentence alert for a parent. Tell them exactly what happened in the chat (mentioning the exact words if relevant) and exactly what practical step they should take with their child. Make it personal, not generic.\n\n"
        "Guidelines:\n"
        "- CRITICAL: If you detect VIOLENCE, AGGRESSION, or BULLYING, set 'is_bullying' to true.\n"
        "- BE NATURAL AND AUTHENTIC. Tailor advice to the exact words used.\n"
        "- All fields MUST be in English. Return ONLY valid JSON."
    )
    
    user_prompt = f"Chat History:\n{history}\n\nLast message from {sender_username}: {message_content}"

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            response_format={ "type": "json_object" },
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        result = json.loads(response.choices[0].message.content)
        
        # התראה להורים (אלגוריתם או AI)
        ai_detected_bullying = result.get("is_bullying", False)
        if is_bullying or ai_detected_bullying:
            parent_alert_text = result.get("parent_alert_text", f"{sender_username} sent a potentially harmful message. Please check in with your child.")
            
            print(f"BULLYING DETECTED! Sender: {sender_username}, AI Detected: {ai_detected_bullying}")
            
            # Alert all parents in the room
            if room_name in rooms:
                for username_in_room, ws_in_room in rooms[room_name].items():
                    if username_in_room in user_relationships:
                        # This user is a parent monitoring someone
                        print(f"ALERTING PARENT IN ROOM: {username_in_room}")
                        child_name = user_relationships.get(username_in_room, 'your child')
                        alert_msg = {
                            "type": "parent_alert",
                            "content": f"Safety Alert ({room_name}): {parent_alert_text}\n\nRecommended: Talk to {child_name} about this."
                        }
                        await ws_in_room.send_text(json.dumps(alert_msg))

        # הפצת ההצעות המעוצבות
        suggestions_list = result.get("suggestions", [])
        if suggestions_list:
            await manager.distribute_suggestions(suggestions_list, room_name, sender_username)

    except Exception as e:
        print(f"AI Error: {e}")

# משתנה גלובלי לניהול שיחות Whisper לכל משתמש
whisper_sessions = {}

# --- Endpoint לשיחה מלאה עם הבוט ---
@app.post("/whisper")
async def whisper_chat(request: Request):
    data = await request.json()
    user_message = data.get("message")
    
    try:
        with open(CHAT_LOG_FILE, "r", encoding="utf-8") as f:
            class_history = f.read()[-3000:] 
    except:
        class_history = "אין היסטוריה זמינה."

    system_prompt = (
        "You are 'Smart Whisper', a personal assistant for a student.\n"
        "1. Strictly answer the student's question based on the provided Chat History.\n"
        "2. If asked about study material (formulas, math) - explain it clearly. DO NOT start teaching new topics if not asked.\n"
        "3. If asked for social advice - give friendly advice.\n"
        "Keep your answers short, concise, and ONLY in English. Do not hallucinate or provide off-topic information."
    )

    # בדיקה אם קיימת שיחה עבור המשתמש
    username = data.get("username", "anonymous")
    session = whisper_sessions.get(username)
    
    if not session:
        session = {
            "messages": [{"role": "system", "content": system_prompt}],
            "turn_count": 0
        }
        whisper_sessions[username] = session

    # Session limit
    if session["turn_count"] >= 15:
        return {"response": "Session limit reached. Please restart the chat for a fresh start."}

    session["messages"].append({"role": "user", "content": f"Chat History:\n{class_history}\n\nQuestion:\n{user_message}"})

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=session["messages"]
        )
        bot_response = response.choices[0].message.content
        session["messages"].append({"role": "assistant", "content": bot_response})
        session["turn_count"] += 1
        return {"response": bot_response}
    except Exception as e:
        return {"response": "Communication error."}


@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str, room_name: str = "Global", parent_of: str = None):
    # Check if user is already in THIS room
    if room_name in rooms and username in rooms[room_name]:
        await websocket.accept()
        await websocket.send_text(json.dumps({"type": "error", "content": "Username taken in this room."}))
        await websocket.close()
        return
    
    # Ensure parent_of is treated as None if empty string
    if not parent_of:
        parent_of = None
        
    print(f"New connection: {username}, Room: {room_name}, Parent of: {parent_of}")
    await manager.connect(websocket, username, room_name, parent_of)
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data["type"] == "chat":
                content = message_data['content']
                
                log_entry = f"[{room_name}] {username}: {content} - {datetime.now()}\n"
                with open(CHAT_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(log_entry)
                
                await manager.broadcast(json.dumps({
                    "type": "message",
                    "content": f"{username}: {content}"
                }), room_name)

                asyncio.create_task(analyze_chat_event(username, content, room_name))

    except WebSocketDisconnect:
        await manager.disconnect(username)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)