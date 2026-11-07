from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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
ADMIN_PASSWORD = "MySecretAdminPassword786" 

def generate_ref_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def init_db():
    conn = sqlite3.connect("earning_app.db")
    cursor = conn.cursor()
    # Users Table with Email and Phone
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            phone TEXT UNIQUE,
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
    # Withdrawals Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            amount INTEGER,
            method TEXT,
            account_number TEXT,
            status TEXT DEFAULT 'Pending',
            time REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

class User(BaseModel):
    username: str
    email: str
    phone: str
    referred_by: Optional[str] = None

class Task(BaseModel):
    username: str
    secret_token: str

class WithdrawalRequest(BaseModel):
    username: str
    secret_token: str
    amount: int
    method: str
    account_number: str

@app.post("/create-user/")
def create_user(user: User):
    conn = sqlite3.connect("earning_app.db")
    cursor = conn.cursor()
    
    # Check if user already exists (Login logic)
    cursor.execute("SELECT * FROM users WHERE username = ?", (user.username,))
    existing_user = cursor.fetchone()
    if existing_user:
        conn.close()
        return {"message": "Logged in successfully!", "balance": existing_user[4]}

    ref_code = generate_ref_code()
    try:
        cursor.execute("INSERT INTO users (username, email, phone, referral_code, referred_by) VALUES (?, ?, ?, ?, ?)", 
                       (user.username, user.email, user.phone, ref_code, user.referred_by))
        if user.referred_by:
            cursor.execute("UPDATE users SET balance = balance + 100 WHERE referral_code = ?", (user.referred_by,))
        conn.commit()
        return {"message": "Account Created Successfully!", "balance": 0, "referral_code": ref_code}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email or Phone already in use by another account!")
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
    if not user: 
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    current_time = time.time()
    if time_col and current_time - user[1] < cooldown:
        conn.close()
        remaining = int(cooldown - (current_time - user[1]))
        raise HTTPException(status_code=429, detail=f"Wait {remaining}s before trying again!")

    new_balance = user[0] + amount
    if time_col:
        cursor.execute(f"UPDATE users SET balance = ?, {time_col} = ? WHERE username = ?", (new_balance, current_time, username))
    else:
        cursor.execute("UPDATE users SET balance = ? WHERE username = ?", (new_balance, username))
    
    conn.commit()
    conn.close()
    return new_balance

@app.post("/add-points/")
def add_points(task: Task): return {"message": "10 Coins Added!", "new_balance": update_balance(task.username, task.secret_token, 10, "last_claim_time", 5)}

@app.post("/watch-video/")
def watch_video(task: Task): return {"message": "30 Coins Added!", "new_balance": update_balance(task.username, task.secret_token, 30, "last_video_time", 20)}

@app.post("/daily-bonus/")
def daily_bonus(task: Task): return {"message": "50 Coins Added!", "new_balance": update_balance(task.username, task.secret_token, 50, "last_daily_bonus", 86400)}

@app.post("/spin-wheel/")
def spin_wheel(task: Task):
    won = random.choice([5, 10, 20, 50])
    return {"message": f"Wheel stopped at {won} Coins!", "new_balance": update_balance(task.username, task.secret_token, won, "last_spin_time", 30)}

@app.post("/scratch-card/")
def scratch_card(task: Task):
    won = random.choice([10, 15, 25, 40])
    return {"message": f"You scratched {won} Coins!", "new_balance": update_balance(task.username, task.secret_token, won, "last_scratch_time", 30)}

@app.post("/request-withdrawal/")
def request_withdrawal(req: WithdrawalRequest):
    if req.secret_token != SECRET_APP_TOKEN: raise HTTPException(status_code=403, detail="Invalid Token")
    if req.amount < 500: raise HTTPException(status_code=400, detail="Minimum withdrawal is 500 Coins!")

    conn = sqlite3.connect("earning_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE username = ?", (req.username,))
    user = cursor.fetchone()
    
    if not user or user[0] < req.amount:
        conn.close()
        raise HTTPException(status_code=400, detail="Insufficient balance!")

    new_balance = user[0] - req.amount
    cursor.execute("UPDATE users SET balance = ? WHERE username = ?", (new_balance, req.username))
    cursor.execute("INSERT INTO withdrawals (username, amount, method, account_number, time) VALUES (?, ?, ?, ?, ?)",
                   (req.username, req.amount, req.method, req.account_number, time.time()))
    conn.commit()
    conn.close()
    return {"message": "Withdrawal request submitted successfully!", "new_balance": new_balance}

# --- ADMIN PANEL ---
@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(password: str = ""):
    if password != ADMIN_PASSWORD:
        return "<h1>Unauthorized! Wrong Password.</h1>"
    
    conn = sqlite3.connect("earning_app.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT username, email, phone, balance, referral_code FROM users")
    users = cursor.fetchall()
    
    cursor.execute("SELECT id, username, amount, method, account_number, status FROM withdrawals")
    withdrawals = cursor.fetchall()
    conn.close()

    html = f"""
    <html>
    <head>
        <title>Admin Dashboard</title>
        <style>
            body {{ font-family: Arial; padding: 20px; background: #f4f4f4; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; background: white; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #007bff; color: white; }}
            h2 {{ color: #333; }}
        </style>
    </head>
    <body>
        <h2>💸 Withdrawal Requests</h2>
        <table>
            <tr><th>ID</th><th>User</th><th>Amount</th><th>Method</th><th>Account Number</th><th>Status</th></tr>
            {''.join(f"<tr><td>{w[0]}</td><td><b>{w[1]}</b></td><td>{w[2]} Coins</td><td>{w[3]}</td><td><b>{w[4]}</b></td><td>{w[5]}</td></tr>" for w in withdrawals)}
        </table>

        <h2>👥 Registered Users (Accounts)</h2>
        <table>
            <tr><th>Username</th><th>Email</th><th>Phone</th><th>Balance</th><th>Invite Code</th></tr>
            {''.join(f"<tr><td><b>{u[0]}</b></td><td>{u[1]}</td><td>{u[2]}</td><td>{u[3]} Coins</td><td>{u[4]}</td></tr>" for u in users)}
        </table>
    </body>
    </html>
    """
    return html
