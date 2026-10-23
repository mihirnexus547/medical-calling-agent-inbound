"""
FastAPI Server for MediFlow AI.
Serves:
1. Static files & Modern Single Page Application (HTML/CSS/JS) on GET /
2. REST APIs for Chat (/api/chat), Doctors (/api/doctors), Availability (/api/availability),
   Appointments (/api/appointments), and Stats (/api/stats).
3. Stripe Webhook (/webhook) and Payment confirmation landing pages.
"""

import os
import time
import json
import asyncio
import re
import uuid
from typing import Optional
import psycopg2
import stripe
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from agents.checkpoint import postgres_checkpointer

load_dotenv()

app = FastAPI(
    title="MediFlow AI | Healthcare Practice API",
    description="Full-stack API serving AI multi-agent reception, Stripe webhooks, and clinic portal.",
    version="2.0.0",
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

# Mount Static Files (CSS, JS, Assets)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")


def get_connection():
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME", "patient_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )
    conn.autocommit = True
    return conn


def get_current_patient(authorization: Optional[str] = None) -> Optional[dict]:
    """Helper to extract patient payload from Bearer token."""
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "").strip()
    return decode_access_token(token)


# ==============================================================================
# FRONTEND ROOT ROUTE
# ==============================================================================
@app.get("/", response_class=FileResponse)
async def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h1>MediFlow AI API Running</h1><p>index.html not found in static/</p>")


# ==============================================================================
# AUTHENTICATION MODELS & ENDPOINTS
# ==============================================================================
class RegisterRequest(BaseModel):
    name: str
    email: str
    phone: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Consultation"


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = "web_default_session"
    token: Optional[str] = None


@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """Register a new patient account with email and password."""
    name = req.name.strip()
    email = req.email.strip().lower()
    phone = req.phone.strip()
    password = req.password.strip()

    if not name or not email or not phone or not password:
        raise HTTPException(status_code=400, detail="All fields (name, email, phone, password) are required.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name, email, phone, password_hash FROM patients WHERE LOWER(email) = %s OR phone = %s;",
            (email, phone),
        )
        existing = cur.fetchone()
        hashed = hash_password(password)

        if existing:
            p_id, p_name, p_email, p_phone, p_hash = existing
            if p_hash:
                raise HTTPException(status_code=400, detail="An account with this email or phone already exists. Please log in.")
            # Patient was previously seeded in clinic without a portal password; activate their account
            cur.execute(
                "UPDATE patients SET name = %s, email = %s, phone = %s, password_hash = %s WHERE id = %s RETURNING id, name, email, phone;",
                (name, email, phone, hashed, p_id),
            )
            patient_row = cur.fetchone()
        else:
            cur.execute(
                "INSERT INTO patients (name, email, phone, password_hash) VALUES (%s, %s, %s, %s) RETURNING id, name, email, phone;",
                (name, email, phone, hashed),
            )
            patient_row = cur.fetchone()

        patient_data = {
            "id": patient_row[0],
            "name": patient_row[1],
            "email": patient_row[2],
            "phone": patient_row[3],
        }
        token = create_access_token({"sub": str(patient_data["id"]), **patient_data})

        # Initialize an initial welcome conversation thread for this patient
        init_thread = f"thread_{patient_data['id']}_{uuid.uuid4().hex[:8]}"
        cur.execute(
            "INSERT INTO chat_conversations (patient_id, thread_id, title) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING;",
            (patient_data["id"], init_thread, "Initial Consultation"),
        )

        return {"token": token, "patient": patient_data, "default_thread_id": init_thread}
    finally:
        cur.close()
        conn.close()


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Authenticate patient via email and password."""
    email = req.email.strip().lower()
    password = req.password.strip()

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name, email, phone, password_hash FROM patients WHERE LOWER(email) = %s;",
            (email,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        p_id, p_name, p_email, p_phone, p_hash = row
        if not p_hash:
            raise HTTPException(
                status_code=400,
                detail="This patient record exists from clinic booking. Please use Sign Up to create your portal password.",
            )

        if not verify_password(password, p_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password.")

        patient_data = {"id": p_id, "name": p_name, "email": p_email, "phone": p_phone}
        token = create_access_token({"sub": str(p_id), **patient_data})

        # Get their latest active conversation or create one
        cur.execute(
            "SELECT thread_id FROM chat_conversations WHERE patient_id = %s ORDER BY updated_at DESC LIMIT 1;",
            (p_id,),
        )
        latest_thread = cur.fetchone()
        if latest_thread:
            thread_id = latest_thread[0]
        else:
            thread_id = f"thread_{p_id}_{uuid.uuid4().hex[:8]}"
            cur.execute(
                "INSERT INTO chat_conversations (patient_id, thread_id, title) VALUES (%s, %s, %s);",
                (p_id, thread_id, "New Consultation"),
            )

        return {"token": token, "patient": patient_data, "default_thread_id": thread_id}
    finally:
        cur.close()
        conn.close()


@app.get("/api/auth/me")
async def get_me(authorization: Optional[str] = Header(None)):
    """Fetch profile of authenticated patient."""
    user = get_current_patient(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"patient": user}


# ==============================================================================
# CONVERSATION THREAD MANAGEMENT (POSTGRES STORED)
# ==============================================================================
@app.get("/api/conversations")
async def list_conversations(authorization: Optional[str] = Header(None)):
    """List all saved conversations for the logged in patient."""
    user = get_current_patient(authorization)
    if not user:
        return []

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, thread_id, title, updated_at
            FROM chat_conversations
            WHERE patient_id = %s
            ORDER BY updated_at DESC;
            """,
            (int(user["sub"]),),
        )
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "thread_id": r[1],
                "title": r[2],
                "updated_at": r[3].strftime("%b %d, %H:%M") if r[3] else "",
            }
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()


@app.post("/api/conversations")
async def create_conversation(req: CreateConversationRequest, authorization: Optional[str] = Header(None)):
    """Create a new conversation session for the patient."""
    user = get_current_patient(authorization)
    patient_id = int(user["sub"]) if user else None

    thread_id = f"thread_{patient_id or 'anon'}_{uuid.uuid4().hex[:8]}"
    title = (req.title or "New Consultation").strip()

    if patient_id:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO chat_conversations (patient_id, thread_id, title)
                VALUES (%s, %s, %s)
                RETURNING id, thread_id, title, updated_at;
                """,
                (patient_id, thread_id, title),
            )
            r = cur.fetchone()
            return {
                "id": r[0],
                "thread_id": r[1],
                "title": r[2],
                "updated_at": r[3].strftime("%b %d, %H:%M") if r[3] else "",
            }
        finally:
            cur.close()
            conn.close()
    else:
        return {"id": 0, "thread_id": thread_id, "title": title, "updated_at": "Just now"}


@app.get("/api/conversations/{thread_id}/messages")
async def get_conversation_messages(thread_id: str):
    """Retrieve all historical messages for a thread directly from PostgresSaver checkpoints."""
    config = {"configurable": {"thread_id": thread_id}}
    tup = postgres_checkpointer.get_tuple(config)
    messages = []

    if tup and "channel_values" in tup.checkpoint:
        raw_msgs = tup.checkpoint["channel_values"].get("messages", [])
        for m in raw_msgs:
            role = getattr(m, "type", None) or getattr(m, "role", "unknown")
            content = getattr(m, "content", "")
            if not content:
                continue

            if role in ("human", "user"):
                # Clean any injected system context tags if present
                clean_content = re.sub(r"^\[Context:[^\]]+\]\s*", "", content)
                messages.append({"role": "user", "content": clean_content})
            elif role in ("ai", "assistant"):
                messages.append({"role": "assistant", "content": content})

    return {"thread_id": thread_id, "messages": messages}


@app.delete("/api/conversations/{thread_id}")
async def delete_conversation(thread_id: str, authorization: Optional[str] = Header(None)):
    """Delete a conversation thread from user's history."""
    user = get_current_patient(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM chat_conversations WHERE thread_id = %s AND patient_id = %s;",
            (thread_id, int(user["sub"])),
        )
        return {"success": True}
    finally:
        cur.close()
        conn.close()


# ==============================================================================
# REST & STREAMING APIS FOR CHAT (PERSISTED VIA POSTGRESSAVER)
# ==============================================================================
def _update_conversation_meta(thread_id: str, patient_id: Optional[int], first_message: str):
    """Helper to update conversation title and updated_at timestamp in Postgres."""
    if not patient_id:
        return
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM chat_conversations WHERE thread_id = %s;", (thread_id,))
        row = cur.fetchone()
        title_snippet = first_message.strip()[:40]
        if len(first_message.strip()) > 40:
            title_snippet += "..."

        if row:
            curr_title = row[1]
            if curr_title in ("New Consultation", "Initial Consultation") and title_snippet:
                cur.execute(
                    "UPDATE chat_conversations SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE thread_id = %s;",
                    (title_snippet, thread_id),
                )
            else:
                cur.execute(
                    "UPDATE chat_conversations SET updated_at = CURRENT_TIMESTAMP WHERE thread_id = %s;",
                    (thread_id,),
                )
        else:
            cur.execute(
                "INSERT INTO chat_conversations (patient_id, thread_id, title) VALUES (%s, %s, %s);",
                (patient_id, thread_id, title_snippet or "Consultation"),
            )
    except Exception:
        pass
    finally:
        if cur: cur.close()
        if conn: conn.close()


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, authorization: Optional[str] = Header(None)):
    """Bridge web chat directly to receptionist_agent with PostgresSaver."""
    from agents.receptionist import receptionist_agent
    from agents.callbacks import AgentLoggingCallback

    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    user = get_current_patient(req.token or authorization)
    patient_id = int(user["sub"]) if user else None

    # Track conversation in Postgres
    _update_conversation_meta(req.thread_id, patient_id, req.message)

    start_t = time.perf_counter()
    try:
        config = {
            "configurable": {"thread_id": req.thread_id},
            "callbacks": [AgentLoggingCallback()],
        }

        agent_input = req.message.strip()
        if user:
            agent_input = (
                f"[Context: Verified Patient ID={user['id']}, Name={user['name']}, Phone={user['phone']}] "
                f"{req.message.strip()}"
            )

        res = receptionist_agent.invoke(
            {"messages": [{"role": "user", "content": agent_input}]},
            config=config,
        )
        latency = time.perf_counter() - start_t
        reply_content = res["messages"][-1].content

        return {
            "reply": reply_content,
            "latency": round(latency, 3),
            "thread_id": req.thread_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest, authorization: Optional[str] = Header(None)):
    """Streaming endpoint for receptionist agent using Server-Sent Events (SSE).
    Persists multi-agent conversations in PostgreSQL via PostgresSaver.
    """
    from agents.receptionist import receptionist_agent
    from agents.callbacks import AgentLoggingCallback

    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    user = get_current_patient(req.token or authorization)
    patient_id = int(user["sub"]) if user else None

    # Update conversation thread metadata in Postgres
    _update_conversation_meta(req.thread_id, patient_id, req.message)

    async def event_generator():
        start_t = time.perf_counter()
        yield f"data: {json.dumps({'status': 'thinking', 'message': 'MediFlow AI consulting clinical records...'})}\n\n"

        loop = asyncio.get_running_loop()
        config = {
            "configurable": {"thread_id": req.thread_id},
            "callbacks": [AgentLoggingCallback()],
        }

        agent_input = req.message.strip()
        if user:
            agent_input = (
                f"[Context: Verified Patient ID={user['id']}, Name={user['name']}, Phone={user['phone']}] "
                f"{req.message.strip()}"
            )

        try:
            res = await loop.run_in_executor(
                None,
                lambda: receptionist_agent.invoke(
                    {"messages": [{"role": "user", "content": agent_input}]},
                    config=config,
                ),
            )
            elapsed = time.perf_counter() - start_t
            reply_content = res["messages"][-1].content or ""

            # Stream response in chunks
            tokens = re.findall(r"\S+|\s+", reply_content)
            for token in tokens:
                yield f"data: {json.dumps({'token': token})}\n\n"
                await asyncio.sleep(0.012)

            yield f"data: {json.dumps({'done': True, 'full_text': reply_content, 'latency': round(elapsed, 3), 'thread_id': req.thread_id})}\n\n"

        except Exception as e:
            err_msg = f"Agent error: {str(e)}"
            yield f"data: {json.dumps({'error': err_msg, 'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/doctors")
async def get_doctors():
    """List all doctors with their specializations and id."""
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, specialization FROM doctors ORDER BY specialization, name;")
        rows = cur.fetchall()
        doctors = [{"id": r[0], "name": r[1], "specialization": r[2]} for r in rows]
        return doctors
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur: cur.close()
        if conn: conn.close()


@app.get("/api/availability")
async def get_availability(doctor_id: int, date: str):
    """Retrieve slot availability for a specific doctor on a given date."""
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Doctor Info
        cur.execute("SELECT name, specialization FROM doctors WHERE id = %s;", (doctor_id,))
        doc_row = cur.fetchone()
        if not doc_row:
            raise HTTPException(status_code=404, detail="Doctor not found")

        doc_name, doc_spec = doc_row

        # Availability Slots
        cur.execute(
            """
            SELECT slot_time, is_booked
            FROM doctor_availability
            WHERE doctor_id = %s AND available_date = %s
            ORDER BY slot_time;
            """,
            (doctor_id, date),
        )
        slots_data = cur.fetchall()

        slots = [
            {
                "start_time": str(r[0]),
                "is_booked": bool(r[1]),
            }
            for r in slots_data
        ]

        return {
            "doctor_id": doctor_id,
            "doctor_name": doc_name,
            "specialization": doc_spec,
            "date": date,
            "slots": slots,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur: cur.close()
        if conn: conn.close()


@app.get("/api/appointments")
async def get_recent_appointments():
    """Return top 20 recent appointments for admin tracking."""
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 
                a.id, 
                COALESCE(p.name, 'Patient #' || a.patient_id) as patient_name,
                a.patient_id,
                d.name as doctor_name, 
                d.specialization,
                a.appointment_date, 
                a.appointment_time, 
                a.status
            FROM appointments a
            LEFT JOIN patients p ON a.patient_id = p.id
            JOIN doctors d ON a.doctor_id = d.id
            ORDER BY a.id DESC
            LIMIT 20;
            """
        )
        rows = cur.fetchall()
        appts = [
            {
                "id": r[0],
                "patient_name": r[1],
                "patient_id": r[2],
                "doctor_name": r[3],
                "specialization": r[4],
                "appointment_date": str(r[5]),
                "appointment_time": str(r[6]),
                "status": r[7],
            }
            for r in rows
        ]
        return appts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur: cur.close()
        if conn: conn.close()


@app.get("/api/stats")
async def get_clinic_stats():
    """Return aggregated live metrics for dashboard."""
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT count(*) FROM patients;")
        total_patients = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM appointments WHERE status = 'booked';")
        active_bookings = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM doctor_availability WHERE available_date >= CURRENT_DATE AND is_booked = FALSE;")
        open_slots = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM invoices WHERE status = 'paid';")
        paid_invoices = cur.fetchone()[0]

        return {
            "total_patients": total_patients,
            "active_bookings": active_bookings,
            "open_slots": open_slots,
            "paid_invoices": paid_invoices,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cur: cur.close()
        if conn: conn.close()


# ==============================================================================
# STRIPE WEBHOOK & PAYMENT LIFECYCLE
# ==============================================================================
@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature") or request.headers.get("STRIPE_SIGNATURE")

    try:
        raw_event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            webhook_secret,
        )
        event = raw_event.to_dict() if hasattr(raw_event, "to_dict") else dict(raw_event)
    except (stripe.error.SignatureVerificationError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {str(e)}")

    if event.get("type") == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        stripe_event_id = event.get("id")
        invoice_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("invoice_id")
        db_conn = None
        cursor = None
        try:
            db_conn = get_connection()
            cursor = db_conn.cursor()

            # Deduplication
            cursor.execute("SELECT 1 FROM payment_events WHERE event_id = %s", (stripe_event_id,))
            if cursor.fetchone():
                return {"status": "already processed"}

            if invoice_id:
                cursor.execute(
                    """
                    UPDATE invoices 
                    SET status = %s, amount_paid_cents = patient_amount_cents, updated_at = CURRENT_TIMESTAMP 
                    WHERE invoice_id = %s
                    """,
                    ("paid", int(invoice_id)),
                )

            cursor.execute(
                """
                INSERT INTO payment_events (event_id, event_type, payload, received_at) 
                VALUES (%s, %s, %s, NOW())
                """,
                (stripe_event_id, event.get("type", "checkout.session.completed"), str(session)),
            )

            db_conn.commit()
        except Exception as e:
            if db_conn:
                db_conn.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        finally:
            if cursor:
                cursor.close()
            if db_conn:
                db_conn.close()

    return {"status": "success"}


@app.get("/payment-success")
async def payment_success(session_id: str = ""):
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Successful | MediFlow AI</title>
        <link rel="stylesheet" href="/static/css/styles.css">
        <style>
            body {{
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                margin: 0;
            }}
            .success-card {{
                background: rgba(16, 26, 46, 0.85);
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 20px;
                padding: 48px 40px;
                text-align: center;
                max-width: 480px;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(20px);
            }}
            .success-icon {{
                font-size: 56px;
                margin-bottom: 20px;
                display: inline-block;
                animation: pulse 2s infinite;
            }}
            .btn-return {{
                margin-top: 24px;
                display: inline-block;
                background: linear-gradient(135deg, #0284c7, #0ea5e9);
                color: #ffffff;
                text-decoration: none;
                font-weight: 700;
                padding: 12px 28px;
                border-radius: 9999px;
                transition: all 0.25s ease;
            }}
            .btn-return:hover {{
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(14, 165, 233, 0.4);
            }}
        </style>
    </head>
    <body>
        <div class="success-card">
            <div class="success-icon">✅</div>
            <h1 style="font-size: 26px; color: #38bdf8; margin-bottom: 12px;">Payment Successful!</h1>
            <p style="color: #94a3b8; font-size: 15px; line-height: 1.6;">Your medical consultation payment has been confirmed and settled. Your appointment is locked in the clinic calendar.</p>
            <div style="margin: 20px 0; background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); color: #38bdf8; padding: 8px 16px; border-radius: 9999px; font-size: 13px; font-family: monospace;">
                Ref: {session_id[:24]}...
            </div>
            <a href="/" class="btn-return">Return to MediFlow Care Portal &rarr;</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/payment-cancelled")
async def payment_cancelled():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Cancelled | MediFlow AI</title>
        <link rel="stylesheet" href="/static/css/styles.css">
    </head>
    <body style="display: flex; align-items: center; justify-content: center; min-height: 100vh;">
        <div style="background: rgba(16, 26, 46, 0.85); border: 1px solid rgba(244, 63, 94, 0.3); border-radius: 20px; padding: 48px 40px; text-align: center; max-width: 480px;">
            <div style="font-size: 52px; margin-bottom: 16px;">🛑</div>
            <h2 style="color: #fb7185; margin-bottom: 12px;">Payment Cancelled</h2>
            <p style="color: #94a3b8; font-size: 15px;">No funds were deducted. You can return to your consultation chat anytime to generate a new payment link or opt to pay at the clinic.</p>
            <a href="/" style="margin-top: 24px; display: inline-block; background: #334155; color: #ffffff; text-decoration: none; padding: 10px 24px; border-radius: 9999px;">Return to Portal</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
