"""Billing and payment link generation tools."""

import os
import time
import uuid
from typing import Optional
from dotenv import load_dotenv
import stripe
from langchain_core.tools import tool

load_dotenv()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

from config import logger, conn, cursor


@tool 
def create_invoice(appointment_id: int, patient_id: int, service_code: str) -> str:
    """Generates a patient invoice. Checks for an existing insurance calculation.
    If none exists, charges the full base price for the service (self-pay).
    """
    start_time = time.perf_counter()
    logger.info("Invoice creation started: appointment_id=%s, patient_id=%s, service_code=%s", appointment_id, patient_id, service_code)
    try:
        check_query = """
            SELECT check_id, visit_cost_cents, insurer_amount_cents, patient_amount_cents
            FROM insurance_checks
            WHERE appointment_id = %s
            ORDER BY checked_at DESC LIMIT 1;
        """
        cursor.execute(check_query, (appointment_id,))
        check_result = cursor.fetchone()

        if check_result:
            check_id, total_cents, insurer_cents, patient_cents = check_result
        else:
            check_id = None
            price_query = "SELECT price_cents FROM service_prices WHERE service_code = %s;"
            cursor.execute(price_query, (service_code,))
            price_result = cursor.fetchone()

            if not price_result:
                return f"Error: Invalid service code {service_code}."
        
            total_cents = price_result[0]
            insurer_cents = 0
            patient_cents = total_cents
        
        idem_key = str(uuid.uuid4())

        insert_invoice = """
            INSERT INTO invoices
            (appointment_id, patient_id, check_id, total_cents, insurer_amount_cents, patient_amount_cents, status, idempotency_key)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
            ON CONFLICT (appointment_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING invoice_id, patient_amount_cents;
        """

        cursor.execute(insert_invoice, (
            appointment_id, patient_id, check_id, total_cents, insurer_cents, patient_cents, idem_key
        ))

        invoice_id, final_patient_owed = cursor.fetchone()
        conn.commit()

        duration = time.perf_counter() - start_time
        logger.info("Invoice created: invoice_id=%s patient_owed=%s duration=%.3fs", invoice_id, final_patient_owed, duration)
        return f"Invoice created successfully! Invoice ID: {invoice_id}. Total: {total_cents} cents, Patient owes: {final_patient_owed} cents."

    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception("Error creating invoice: %s", e)
        return f"Error creating invoice: {str(e)}"


@tool
def generate_payment_link(invoice_id: int, delivery_channel: str = "sms") -> str:
    """Generates a Stripe Checkout payment link for an existing invoice, records the payment attempt,
    and updates the invoice status to 'link_sent'.
    delivery_channel must be either 'sms' or 'email'.
    """
    start_time = time.perf_counter()
    logger.info("Generating payment link started: invoice_id=%s, channel=%s", invoice_id, delivery_channel)

    if delivery_channel not in ("sms", "email"):
        delivery_channel = "sms"

    try:
        cursor.execute(
            """
            SELECT patient_id, appointment_id, patient_amount_cents, currency, status
            FROM invoices
            WHERE invoice_id = %s;
            """,
            (invoice_id,),
        )
        invoice = cursor.fetchone()

        if not invoice:
            return f"Error: Invoice ID {invoice_id} not found."

        patient_id, appt_id, patient_amount_cents, currency, status = invoice

        if status == "paid":
            return f"Invoice {invoice_id} is already paid in full."

        if patient_amount_cents <= 0:
            cursor.execute(
                "UPDATE invoices SET status = 'paid', updated_at = CURRENT_TIMESTAMP WHERE invoice_id = %s;",
                (invoice_id,),
            )
            conn.commit()
            return f"Invoice {invoice_id} has a 0-cent patient balance. Marked as paid—no payment link needed."

        # Create Stripe Checkout Session
        if stripe.api_key:
            session = stripe.checkout.Session.create(
                line_items=[
                    {
                        "price_data": {
                            "currency": currency,
                            "product_data": {
                                "name": f"Medical Appointment #{appt_id} (Invoice #{invoice_id})",
                            },
                            "unit_amount": patient_amount_cents,
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url="http://localhost:8000/payment-success?session_id={CHECKOUT_SESSION_ID}",
                cancel_url="http://localhost:8000/payment-cancelled",
                client_reference_id=str(invoice_id),
                metadata={
                    "invoice_id": str(invoice_id),
                    "patient_id": str(patient_id),
                    "appointment_id": str(appt_id),
                },
            )
            provider_ref = session.id
            payment_url = session.url
        else:
            provider_ref = f"cs_test_{uuid.uuid4().hex[:16]}"
            payment_url = f"https://checkout.stripe.com/pay/{provider_ref}"

        cursor.execute(
            """
            INSERT INTO payments
            (invoice_id, provider, provider_ref, payment_url, amount_cents, status, sent_via)
            VALUES (%s, 'stripe', %s, %s, %s, 'sent', %s)
            RETURNING payment_id;
            """,
            (invoice_id, provider_ref, payment_url, patient_amount_cents, delivery_channel),
        )
        payment_id = cursor.fetchone()[0]

        cursor.execute(
            """
            UPDATE invoices
            SET status = 'link_sent', updated_at = CURRENT_TIMESTAMP
            WHERE invoice_id = %s;
            """,
            (invoice_id,),
        )
        conn.commit()

        duration = time.perf_counter() - start_time
        logger.info(
            "Payment link generated: payment_id=%s invoice_id=%s duration=%.3fs",
            payment_id,
            invoice_id,
            duration,
        )

        return (
            f"Payment link generated successfully!\n"
            f"Amount Due: ${patient_amount_cents / 100:.2f}\n"
            f"Payment Link: {payment_url}\n"
            f"INSTRUCTION: You must provide this exact Payment Link URL directly to the user in your response so they can click and complete payment."
        )

    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception("Failed to generate payment link for invoice_id=%s", invoice_id)
        return f"Error generating payment link: {str(e)}"


@tool
def check_invoice_payment_status(patient_id: int, invoice_id: Optional[int] = None, appointment_id: Optional[int] = None) -> str:
    """Check the payment and invoice status for a patient by invoice_id, appointment_id, or patient_id."""
    start_time = time.perf_counter()
    logger.info("Checking invoice payment status: patient_id=%s, invoice_id=%s, appointment_id=%s", patient_id, invoice_id, appointment_id)
    try:
        if invoice_id:
            query = """
                SELECT invoice_id, appointment_id, total_cents, patient_amount_cents, amount_paid_cents, status, updated_at
                FROM invoices
                WHERE invoice_id = %s AND patient_id = %s;
            """
            cursor.execute(query, (invoice_id, patient_id))
        elif appointment_id:
            query = """
                SELECT invoice_id, appointment_id, total_cents, patient_amount_cents, amount_paid_cents, status, updated_at
                FROM invoices
                WHERE appointment_id = %s AND patient_id = %s
                ORDER BY created_at DESC LIMIT 1;
            """
            cursor.execute(query, (appointment_id, patient_id))
        else:
            query = """
                SELECT invoice_id, appointment_id, total_cents, patient_amount_cents, amount_paid_cents, status, updated_at
                FROM invoices
                WHERE patient_id = %s
                ORDER BY created_at DESC LIMIT 1;
            """
            cursor.execute(query, (patient_id,))

        invoice = cursor.fetchone()
        if not invoice:
            return f"No invoice or payment records found for patient ID {patient_id}."

        inv_id, appt_id, total_cents, patient_cents, paid_cents, status, updated_at = invoice

        total_dollars = total_cents / 100.0
        patient_dollars = patient_cents / 100.0
        paid_dollars = paid_cents / 100.0

        if status == "paid":
            return (
                f"Invoice #{inv_id} for Appointment #{appt_id} is PAID IN FULL (${paid_dollars:.2f}). "
                f"No balance remaining. Thank you!"
            )
        elif status == "link_sent":
            return (
                f"Invoice #{inv_id} for Appointment #{appt_id}: Status is 'link_sent' (payment pending). "
                f"Total visit cost: ${total_dollars:.2f}. Patient owes: ${patient_dollars:.2f}. "
                f"Awaiting checkout completion via Stripe."
            )
        else:
            return (
                f"Invoice #{inv_id} for Appointment #{appt_id}: Status is '{status}'. "
                f"Total visit cost: ${total_dollars:.2f}. Patient owes: ${patient_dollars:.2f}."
            )

    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception("Failed checking invoice payment status: %s", e)
        return f"Error retrieving invoice status: {str(e)}"
