"""
Multi-Agent Inbound Calling System Orchestrator.
Refactored to cleanly import from modular packages:
- `config`: Database connections and logging
- `tools`: Patient, Appointment, Insurance, and Billing tools
- `agents`: Receptionist, Appointment, Insurance, and Billing specialized agents
"""

import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

# LangSmith tracing settings
os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_PROJECT"] = "mca_multiagent_inbound"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"

# Import database & logging
from config import conn, cursor, logger

# Import all tools
from tools import (
    check_patients_exist,
    insert_patient,
    update_patient_records,
    resolve_relative_date,
    resolve_date_helper,
    get_calendar_context,
    list_doctors_and_specializations,
    check_available_slots,
    book_appointment,
    get_patient_appointments,
    cancel_appointment,
    reschedule_appointment,
    check_insurance_eligibility,
    create_invoice,
    generate_payment_link,
    check_invoice_payment_status,
)

# Import agents and callbacks
from agents import (
    receptionist_agent as agent,
    appointment_agent,
    insurance_agent,
    billing_agent,
    handoff_to_appointment_agent,
    handoff_to_insurance,
    handoff_to_billing,
    AgentLoggingCallback,
    thread_config,
)

import stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


def main():
    logger.info("Receptionist agent initialized")
    print("Receptionist & Appointment system initialized. Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("User: ")
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break

        if user_input.strip().lower() in ["exit", "quit"]:
            logger.info("Receptionist session ended")
            break

        start_time = time.perf_counter()
        logger.info("Agent request started")

        try:
            response = agent.invoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config={**thread_config, "callbacks": [AgentLoggingCallback()]},
            )

            elapsed = time.perf_counter() - start_time
            logger.info("Agent request completed: latency=%.3fs", elapsed)

            print(f"Agent: {response['messages'][-1].content}")
            print(f"Latency: {elapsed:.2f} seconds\n")

        except Exception:
            elapsed = time.perf_counter() - start_time
            logger.exception("Agent request failed after %.3fs", elapsed)
            print("Sorry, something went wrong. Please try again.\n")


if __name__ == "__main__":
    main()