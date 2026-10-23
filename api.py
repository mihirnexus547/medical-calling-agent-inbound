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
from typing import Optional
import psycopg2
import stripe
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "patient_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )


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
# REST APIS FOR WEB PORTAL
# ==============================================================================
class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = "web_default_session"


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Bridge web chat directly to receptionist_agent."""
    from agents.receptionist import receptionist_agent
    from agents.callbacks import AgentLoggingCallback

    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    start_t = time.perf_counter()
    try:
        config = {
            "configurable": {"thread_id": req.thread_id},
            "callbacks": [AgentLoggingCallback()],
        }
        res = receptionist_agent.invoke(
            {"messages": [{"role": "user", "content": req.message.strip()}]},
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
