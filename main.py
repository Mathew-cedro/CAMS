import sqlite3
import os
import json
import httpx
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

DATABASE_FILE = "cams.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE_FILE, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    # Enforce foreign keys so deleting a program deletes its beneficiaries automatically
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def check_and_init_db():
    if os.path.exists(DATABASE_FILE):
        print(f"✅ DB '{DATABASE_FILE}' exists. Skipping creation.")
        return
    
    print(f"⚠️ DB '{DATABASE_FILE}' not found. Building advanced dynamic schema...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Users
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL, locked INTEGER DEFAULT 0)''')
    # 2. Programs
    cursor.execute('''CREATE TABLE IF NOT EXISTS programs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, budget REAL DEFAULT 0.0, status TEXT NOT NULL DEFAULT 'Active')''')
    # 3. Dynamic Fields Schema (Links to a specific program)
    cursor.execute('''CREATE TABLE IF NOT EXISTS program_fields (id INTEGER PRIMARY KEY AUTOINCREMENT, program_id INTEGER, name TEXT, type TEXT, FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE CASCADE)''')
    # 4. Beneficiaries (Stores dynamic form answers as JSON strings)
    cursor.execute('''CREATE TABLE IF NOT EXISTS beneficiaries (id INTEGER PRIMARY KEY AUTOINCREMENT, program_id INTEGER, values_json TEXT, FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE CASCADE)''')
    
    # Seed Master Accounts
    cursor.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', 'admin123', 'Admin'), ('staff', 'staff123', 'Staff')")
    
    conn.commit()
    conn.close()
    print(f"✅ Database successfully built.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    check_and_init_db()
    yield

app = FastAPI(lifespan=lifespan)

# Allow frontend to talk to backend
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- DATA MODELS ---
class LoginRequest(BaseModel):
    username: str
    password: str

class FieldModel(BaseModel):
    name: str
    type: str

class ProgramModel(BaseModel):
    name: str
    budget: float
    fields: List[FieldModel]

class BeneficiaryModel(BaseModel):
    values: Dict[str, Any]

class UserModel(BaseModel):
    username: str
    password: str
    role: str

# --- ENDPOINTS ---
@app.post("/api/login")
def process_login(request: LoginRequest):
    conn = get_db_connection()
    user = conn.execute("SELECT username, role FROM users WHERE username = ? AND password = ?", (request.username, request.password)).fetchone()
    conn.close()
    if user:
        return {"status": "success", "user": {"username": user["username"], "role": user["role"]}}
    return {"status": "error", "message": "Invalid credentials"}

# The Master Synchronization Endpoint
@app.get("/api/state")
def get_full_state():
    conn = get_db_connection()
    
    # Get users
    users = [dict(u) for u in conn.execute("SELECT username, role, locked FROM users").fetchall()]
    for u in users:
        u['locked'] = bool(u['locked'])
        
    # Get programs, their dynamic fields, and their beneficiaries
    programs_raw = conn.execute("SELECT * FROM programs").fetchall()
    programs = []
    for p in programs_raw:
        prog_dict = dict(p)
        prog_id = p["id"]
        
        # Assemble fields
        fields = [dict(f) for f in conn.execute("SELECT name, type FROM program_fields WHERE program_id = ?", (prog_id,)).fetchall()]
        prog_dict["fields"] = fields
        
        # Assemble beneficiaries (Parse JSON string back to dictionary)
        bens_raw = conn.execute("SELECT id, values_json FROM beneficiaries WHERE program_id = ?", (prog_id,)).fetchall()
        bens = [{"id": b["id"], "values": json.loads(b["values_json"])} for b in bens_raw]
        prog_dict["beneficiaries"] = bens
        
        programs.append(prog_dict)
        
    conn.close()
    return {"programs": programs, "users": users}

@app.post("/api/programs")
def create_program(prog: ProgramModel):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO programs (name, budget) VALUES (?, ?)", (prog.name, prog.budget))
    prog_id = cursor.lastrowid
    
    for f in prog.fields:
        cursor.execute("INSERT INTO program_fields (program_id, name, type) VALUES (?, ?, ?)", (prog_id, f.name, f.type))
    
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.put("/api/programs/{prog_id}/close")
def close_program(prog_id: int):
    conn = get_db_connection()
    conn.execute("UPDATE programs SET status = 'Closed' WHERE id = ?", (prog_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/programs/{prog_id}")
def delete_program(prog_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM programs WHERE id = ?", (prog_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/programs/{prog_id}/beneficiaries")
def add_beneficiary(prog_id: int, ben: BeneficiaryModel):
    conn = get_db_connection()
    # Serialize dynamic dictionary to JSON string for SQLite storage
    conn.execute("INSERT INTO beneficiaries (program_id, values_json) VALUES (?, ?)", (prog_id, json.dumps(ben.values)))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/api/beneficiaries/{ben_id}")
def delete_beneficiary(ben_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM beneficiaries WHERE id = ?", (ben_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/users")
def add_user(user: UserModel):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (user.username, user.password, user.role))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return {"status": "error", "message": "Username exists"}
    conn.close()
    return {"status": "success"}

@app.delete("/api/users/{username}")
def revoke_user(username: str):
    conn = get_db_connection()
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/reports/ai-summary")
async def generate_ai_summary():
    conn = get_db_connection()
    total_bens = conn.execute("SELECT COUNT(*) FROM beneficiaries").fetchone()[0]
    total_progs = conn.execute("SELECT COUNT(*) FROM programs WHERE status='Active'").fetchone()[0]
    conn.close()
    prompt = f"System data: {total_bens} registered beneficiaries across {total_progs} active programs. Write a 1-sentence executive summary of this status for a local government mayor."
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("http://localhost:11434/api/generate", json={"model": "tinyllama", "prompt": prompt, "stream": False}, timeout=40.0)
            ai_text = response.json().get("response", "")
            return {"status": "success", "summary": ai_text.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}