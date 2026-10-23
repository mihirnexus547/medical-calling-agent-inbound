"""Billing Agent definition and handoff tool."""

import time
from langchain.agents import create_agent
from langchain_core.tools import tool
from config import logger
from tools.billing_tools import (
    create_invoice,
    generate_payment_link,
    check_invoice_payment_status,
)
from agents.callbacks import AgentLoggingCallback
from agents.checkpoint import postgres_checkpointer as checkpointer


@tool 
def handoff_to_billing(patient_id: int, request: str) -> str:
    """Call this tool to transfer the user to the billing agent to create or view an invoice or check payment status."""
    start_time = time.perf_counter()
    logger.info("Handoff to Billing Agent started: patient_id=%s, request=%s", patient_id, request)
    try:
        billing_config = {
            "configurable": {"thread_id": f"billing_patient_{patient_id}"},
            "callbacks": [AgentLoggingCallback()],
        }
        response = billing_agent.invoke(
            {"messages": [{"role": "user", "content": f"Patient ID: {patient_id}, Request: {request}"}]},
            config=billing_config,
        )
        duration = time.perf_counter() - start_time
        logger.info("Handoff to Billing Agent completed: patient_id=%s duration=%.3fs", patient_id, duration)
        return response["messages"][-1].content
    except Exception as e:
        logger.exception("Handoff to Billing Agent failed: %s", e)
        return f"Failed to process billing request: {str(e)}"


def _get_handoff_to_insurance():
    from agents.insurance import handoff_to_insurance
    return handoff_to_insurance


import os
from dotenv import load_dotenv

load_dotenv()

from agents import get_chat_llm

billing_agent = create_agent(
    model=get_chat_llm(temperature=0.1),
    system_prompt=(
        "You are the Billing Agent, a specialized AI assistant.\n"
        "Your ONLY job is to manage invoices, generate payment links, and check payment status for patients.\n"
        "Rules:\n"
        "1. When the user asks if a payment is done, completed, or asks to check invoice/payment status, ALWAYS call the check_invoice_payment_status tool.\n"
        "2. When asked to generate a bill or invoice, ALWAYS run the create_invoice tool first. If service_code is not specified, default to 'CONSULT'.\n"
        "3. Once create_invoice returns the invoice_id, call generate_payment_link with that invoice_id. ALWAYS output the full, clickable Stripe URL directly in your response so the patient can click it to pay.\n"
        "4. Never call more than one tool in a single turn.\n"
        "5. Never calculate copays yourself; rely entirely on the tool's logic.\n"
        "6. If the user asks to check coverage or calculate a copay first, IMMEDIATELY call the handoff_to_insurance tool and relay its response directly to the user."
    ),
    tools=[check_invoice_payment_status, create_invoice, generate_payment_link, _get_handoff_to_insurance()],
    checkpointer=checkpointer,
)
