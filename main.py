#updated file

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from S3.app import app as chat_app
from S3.app import app as chat_app

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the chat application
app.mount("/chat", chat_app)

@app.get("/")
async def root():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Unified School App</title>
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Poppins', sans-serif;
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                margin: 0;
            }
            .container {
                background: rgba(255, 255, 255, 0.9);
                padding: 3rem;
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                text-align: center;
                max-width: 600px;
            }
            h1 { color: #2c3e50; margin-bottom: 1.5rem; }
            p { color: #546e7a; margin-bottom: 2rem; font-size: 1.1rem; }
            .links {
                display: flex;
                gap: 15px;
                justify-content: center;
                flex-wrap: wrap;
            }
            a {
                text-decoration: none;
                color: white;
                padding: 12px 24px;
                border-radius: 30px;
                font-weight: 600;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            a:hover {
                transform: translateY(-3px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            }
            .btn-chat { background: linear-gradient(135deg, #4F46E5, #6366f1); }
            .btn-learn { background: linear-gradient(135deg, #2563EB, #3b82f6); }
            .btn-recess { background: linear-gradient(135deg, #8B5CF6, #a78bfa); }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Welcome to the Unified School App 🎓</h1>
            <p>Welcome to the secure school communication platform.</p>
            <div class="links">
                <a href="/chat/" class="btn-chat">💬 Enter Main Chat</a>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

if __name__ == "__main__":
    import uvicorn
    # Run the unified app on a single port
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)



