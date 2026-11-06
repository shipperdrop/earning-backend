from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import time
import random
import string
from typing import Optional

app = FastAPI(title="Max Earning API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_APP_TOKEN = "MySuperSecretAppToken123"

def generate_ref_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def init_db():
    conn = sqlite3.connect("earning_app.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            balance INTEGER DEFAULT 0,
            last_claim_time REAL DEFAULT 0,
            last_daily_bonus REAL DEFAULT 0,
            last_spin_time REAL DEFAULT 0,
            last_scratch_time REAL DEFAULT 0,
            last_video_time REAL DEFAULT 0,
            referral_code TEXT UNIQUE,
            referred_by TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

class User(BaseModel):
    username: str
    referred_by: Optional[str] = None

class Task(BaseModel):
    username: str
    secret_token: str

class MathTask(BaseModel):
    username: str
    secret_token: str
    is_correct: bool

@app.post("/create-user/")
def create_user(user: User):
    conn = sqlite3.connect("earning_app.db")
    cursor = conn.cursor()
    ref_code = generate_ref_code()
    try:
        cursor.execute("INSERT INTO users (username, referral_code, referred_by) VALUES (?, ?, ?)", 
                       (user.username, ref_code, user.referred_by))
        if user.referred_by:
            cursor.execute("UPDATE users SET balance = balance + 100 WHERE referral_code = ?", (user.referred_by,))
        conn.commit()
        return {"message": "Account Created!", "balance": 0, "referral_code": ref_code}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
    finally:
        conn.close()

@app.get("/user-info/{username}")
def get_user_info(username: str):
    conn = sqlite3.connect("earning_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, referral_code FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    return {"username": username, "balance": user[0], "referral_code": user[1]}

def update_balance(username, token, amount, time_col=None, cooldown=0):
    if token != SECRET_APP_TOKEN: raise HTTPException(status_code=403, detail="Invalid Token")
    conn = sqlite3.connect("earning_app.db")
    cursor = conn.cursor()
    
    query = f"SELECT balance" + (f", {time_col}" if time_col else "") + " FROM users WHERE username = ?"
    cursor.execute(query, (username,))
    user = cursor.fetchone()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    current_time = time.time()
    if time_col and current_time - user[1] < cooldown:
        conn.close()
        raise HTTPException(status_code=429, detail="Task is locked. Please wait!")

    new_balance = user[0] + amount
    if time_col:
        cursor.execute(f"UPDATE users SET balance = ?, {time_col} = ? WHERE username = ?", (new_balance, current_time, username))
    else:
        cursor.execute("UPDATE users SET balance = ? WHERE username = ?", (new_balance, username))
    
    conn.commit()
    conn.close()
    return new_balance

# 1. Normal Ad (5s)
@app.post("/add-points/")
def add_points(task: Task):
    bal = update_balance(task.username, task.secret_token, 10, "last_claim_time", 5)
    return {"message": "10 Coins Added!", "new_balance": bal}

# 2. Premium Video Ad (30s video) - 30 Coins
@app.post("/watch-video/")
def watch_video(task: Task):
    bal = update_balance(task.username, task.secret_token, 30, "last_video_time", 30)
    return {"message": "30 Coins Added for Video!", "new_balance": bal}

# 3. Daily Bonus (24h)
@app.post("/daily-bonus/")
def daily_bonus(task: Task):
    bal = update_balance(task.username, task.secret_token, 50, "last_daily_bonus", 86400)
    return {"message": "50 Coins Daily Bonus Added!", "new_balance": bal}

# 4. Spin Wheel (1h)
@app.post("/spin-wheel/")
def spin_wheel(task: Task):
    won = random.choice([5, 10, 20, 50])
    bal = update_balance(task.username, task.secret_token, won, "last_spin_time", 3600)
    return {"message": f"Wheel stopped at {won} Coins!", "new_balance": bal}

# 5. Scratch Card (2h)
@app.post("/scratch-card/")
def scratch_card(task: Task):
    won = random.choice([10, 15, 25, 40])
    bal = update_balance(task.username, task.secret_token, won, "last_scratch_time", 7200)
    return {"message": f"You scratched {won} Coins!", "new_balance": bal}

# 6. Math Quiz (Solve simple math for 5 points, no cooldown)
@app.post("/solve-math/")
def solve_math(task: MathTask):
    if not task.is_correct: raise HTTPException(status_code=400, detail="Wrong Answer!")
    bal = update_balance(task.username, task.secret_token, 5) # 5 points per correct math
    return {"message": "Correct Answer! 5 Coins Added.", "new_balance": bal}

# 7. Offerwall Postback (Advanced - When CPALead sends successful task completion)
@app.get("/offerwall-webhook")
def offerwall_postback(username: str, reward: int):
    # CPALead aapke is URL par hit karega jab user unka task karega
    conn = sqlite3.connect("earning_app.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE username = ?", (reward, username))
    conn.commit()
    conn.close()
    return {"status": "success"}