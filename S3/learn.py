from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
import json
from dotenv import load_dotenv
from openai import OpenAI
import os
from datetime import datetime

app = FastAPI()

# Load environment variables from .env file
load_dotenv()

openai_api_key = os.getenv("OPENAI_API")
if not openai_api_key:
    openai_api_key = "MISSING_KEY"

client = OpenAI(
    api_key=openai_api_key,
    base_url="https://api.groq.com/openai/v1"
)

# הגדרת מיקום הקובץ ושמירה מחדש בכל אתחול
CHAT_LOG_FILE = "logs/learn_history.txt"
if not os.path.exists("logs"):
    os.makedirs("logs")
with open(CHAT_LOG_FILE, "w", encoding="utf-8") as f:
    f.write("")

# ניהול חיבורי המשתמשים לצ'אט
connected_clients = {}

# מנהל חיבורים
class ConnectionManager:
    async def connect(self, websocket: WebSocket, username: str):
        await websocket.accept()
        connected_clients[username] = websocket
        # הודעה לכל המשתמשים על הצטרפות
        await self.broadcast(json.dumps({
            "type": "message", 
            "content": f"{username} has joined the chat"
        }))
        await self.send_user_list()
    
    async def disconnect(self, username: str):
        if username in connected_clients:
            del connected_clients[username]
            await self.broadcast(json.dumps({
                "type": "message", 
                "content": f"{username} has left the chat"
            }))
            if username in whisper_sessions:
                del whisper_sessions[username]
            await self.send_user_list()
    
    async def send_personal_message(self, message: str, username: str):
        if username in connected_clients:
            await connected_clients[username].send_text(message)
    
    async def broadcast(self, message: str):
        for username, connection in connected_clients.items():
            await connection.send_text(message)
    
    async def send_user_list(self):
        users_list = list(connected_clients.keys())
        for username, connection in connected_clients.items():
            await connection.send_text(json.dumps({
                "type": "users", 
                "users": users_list
            }))

manager = ConnectionManager()

# Serve the HTML file
@app.get("/")
async def get():
    with open("S3/index1.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

# WebSocket endpoint עבור הצ'אט
@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    if username in connected_clients:
        await websocket.accept()
        await websocket.send_text(json.dumps({
            "type": "error", 
            "content": "Username already taken. Please choose another one."
        }))
        await websocket.close()
        return
    
    await manager.connect(websocket, username)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            if message_data["type"] == "chat":
                # שמירת ההודעה בקובץ
                log_entry = f"{username}: {message_data['content']} -at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                with open(CHAT_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(log_entry)
                
                await manager.broadcast(json.dumps({
                    "type": "message",
                    "content": f"{username}: {message_data['content']}"
                }))
    except WebSocketDisconnect:
        await manager.disconnect(username)

# משתנה גלובלי לניהול שיחות Whisper לכל משתמש
whisper_sessions = {}

SYSTEM_PROMPT_WHISPER = (
    "You are a supportive, friendly, and educational bot. Your task is to provide direct guidance based STRICTLY on the current Chat History. "
    "DO NOT ask 'Would you like some advice?'. Instead, immediately say what is happening and provide a suggested response. "
    "Example: 'It seems there is a disagreement. You should say: Let's try to find a solution.' "
    "Keep it very brief (2-3 sentences max). Your responses MUST be in English."
)

# Endpoint ל־Whisper AI
@app.post("/whisper")
async def whisper_ai(request: Request):
    data = await request.json()
    username = data.get("username")
    user_message = data.get("message", "").strip()  # הודעת תלמיד, יכולה להיות ריקה לקריאה ראשונית

    # בדיקה אם קיימת שיחה עבור המשתמש
    session = whisper_sessions.get(username)
    if not session:
        # יצירת session חדש עם הודעה ראשונית הכוללת את היסטוריית הצ'אט
        with open(CHAT_LOG_FILE, "r", encoding="utf-8") as f:
            learn_history = f.read()
        initial_user_message = f"Chat History:\n{learn_history}\n\nPlease provide guidance and support for the student: {username} based on the chat history."
        conversation = [
            {"role": "system", "content": SYSTEM_PROMPT_WHISPER},
            {"role": "user", "content": initial_user_message}
        ]
        session = {"conversation": conversation, "turn_count": 0}
        whisper_sessions[username] = session

    # אם השיחה הגיעה למגבלת 5 חילופי דברים, החזר הודעה מתאימה
    elif session["turn_count"] >= 10:
        return {"response": "The conversation has reached its limit. To finish, close the window and start a new conversation."}

    # אם התקבלה הודעת תלמיד – הוסף להקשר השיחה
    else:
        with open(CHAT_LOG_FILE, "r", encoding="utf-8") as f:
            learn_history = f.read()
        session["conversation"].append({"role": "user", "content": f"Chat History:\n{learn_history}\n\nThe student replied: {user_message}"})

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=session["conversation"],
            max_tokens=2000
        )
        assistant_message = response.choices[0].message.content
        session["conversation"].append({"role": "assistant", "content": assistant_message})
        session["turn_count"] += 1
    except Exception as e:
        assistant_message = f"Error: {str(e)}"
    return {"response": assistant_message}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
