import stripe 
import os 
from fastapi import FastAPI, Request, HTTPException
import psycopg2
from dotenv import load_dotenv

load_dotenv()


app = FastAPI(title="Medical Billing Webhook Server")
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

def get_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "patient_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )

@app.post("/webhook")
async def stripe_webhook(request: Request):
    # Get the raw payload and signature
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature") or request.headers.get("STRIPE_SIGNATURE")

    try:
        # verify it's really from Stripe
        raw_event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            webhook_secret
        )
        event = raw_event.to_dict() if hasattr(raw_event, "to_dict") else dict(raw_event)
    except (stripe.error.SignatureVerificationError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid signature: {str(e)}")
    
    # Handle the successful payment event
    if event.get("type") == "checkout.session.completed":
        session = event.get('data', {}).get('object', {})
        stripe_event_id = event.get('id')
        invoice_id = session.get('client_reference_id') or (session.get('metadata') or {}).get('invoice_id')
        db_conn = None
        cursor = None
        try:
            db_conn = get_connection()
            cursor = db_conn.cursor()

            # Deduplication check 
            cursor.execute("SELECT 1 FROM payment_events WHERE event_id = %s", (stripe_event_id,))
            if cursor.fetchone():
                return {"status": "already processed"}
            
            if invoice_id:
                cursor.execute(
                    "UPDATE invoices SET status = %s, amount_paid_cents = patient_amount_cents, updated_at = CURRENT_TIMESTAMP WHERE invoice_id = %s",
                    ("paid", int(invoice_id))
                )
            
            cursor.execute(
                "INSERT INTO payment_events (event_id, event_type, payload, received_at) VALUES (%s, %s, %s, NOW())",
                (stripe_event_id, event.get("type", "checkout.session.completed"), str(session))
            )

            db_conn.commit()
        except Exception as e:
            if db_conn: db_conn.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        finally:
            if cursor: cursor.close()
            if db_conn: db_conn.close()

    return {"status": "success"}


@app.get("/payment-success")
async def payment_success(session_id: str = ""):
    from fastapi.responses import HTMLResponse
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Payment Successful</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: #0f172a;
                color: #f8fafc;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
            }}
            .card {{
                background: #1e293b;
                padding: 40px;
                border-radius: 16px;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4);
                text-align: center;
                max-width: 440px;
                border: 1px solid #334155;
            }}
            .icon {{
                font-size: 52px;
                margin-bottom: 16px;
            }}
            h1 {{ font-size: 24px; color: #38bdf8; margin-bottom: 12px; }}
            p {{ font-size: 15px; color: #94a3b8; line-height: 1.6; margin-bottom: 24px; }}
            .badge {{
                display: inline-block;
                padding: 6px 12px;
                background: rgba(56, 189, 248, 0.15);
                color: #38bdf8;
                border-radius: 20px;
                font-size: 13px;
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">✅</div>
            <h1>Payment Successful!</h1>
            <p>Your payment has been received and processed. Your medical appointment is confirmed.</p>
            <div class="badge">Session: {session_id[:18]}...</div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/payment-cancelled")
async def payment_cancelled():
    from fastapi.responses import HTMLResponse
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>Payment Cancelled</title></head>
    <body style="font-family: sans-serif; text-align: center; padding: 50px; background: #0f172a; color: #f8fafc;">
        <h2>Payment Cancelled</h2>
        <p style="color: #94a3b8;">No charge was made. You can return to your calling assistant to request a new link.</p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

