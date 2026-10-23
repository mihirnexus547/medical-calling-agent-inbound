"""Receptionist agent definition (includes handoffs to appointment, insurance, and billing agents)."""

import time
from datetime import date

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver

from config import logger
from tools import (
    check_patients_exist,
    insert_patient,
    update_patient_records,
    get_calendar_context,
)
from agents.callbacks import AgentLoggingCallback


@tool
def handoff_to_appointment_agent(patient_id: int, request_details: str) -> str:
    """Synchronously invoke the Appointment Agent and return its response directly to the user.
    Use this for ALL doctor lookups, slot checks, booking, rescheduling, canceling, and viewing
    appointments. The response from this tool IS the answer — relay it verbatim to the user
    without adding any commentary."""
    from agents.appointment import appointment_agent

    start_time = time.perf_counter()
    logger.info(
        "Handoff to Appointment Agent started: patient_id=%s, request_details=%s",
        patient_id,
        request_details,
    )

    try:
        appt_thread_config = {
            "configurable": {"thread_id": f"appt_patient_{patient_id}"},
            "callbacks": [AgentLoggingCallback()],
        }

        today_str = date.today().strftime("%A, %Y-%m-%d")
        response = appointment_agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"[System Date: Today is {today_str}] "
                            f"Patient ID:{patient_id}, Request:{request_details}"
                        ),
                    }
                ]
            },
            config=appt_thread_config,
        )

        duration = time.perf_counter() - start_time
        logger.info(
            "Handoff to Appointment Agent completed: patient_id=%s duration=%.3fs",
            patient_id,
            duration,
        )
        return response["messages"][-1].content

    except Exception:
        duration = time.perf_counter() - start_time
        logger.exception(
            "Handoff to Appointment Agent failed: patient_id=%s duration=%.3fs",
            patient_id,
            duration,
        )
        return "Failed to process appointment request with the appointment agent. Please try again."


@tool
def handful_to_appointment_agent(patient_id: int, request_details: str) -> str:
    """Alias for handoff_to_appointment_agent (for appointment bookings, slots, doctors, cancellations)."""
    return handoff_to_appointment_agent.invoke({"patient_id": patient_id, "request_details": request_details})


def _get_handoff_to_insurance():
    from agents.insurance import handoff_to_insurance
    return handoff_to_insurance


def _get_handoff_to_billing():
    from agents.billing import handoff_to_billing
    return handoff_to_billing


import os
from dotenv import load_dotenv

load_dotenv()

checkpointer = InMemorySaver()

import re

_raw_receptionist_agent = create_agent(
    model=ChatGroq(model_name=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), temperature=0.1),
    system_prompt=(
        f"{get_calendar_context()}\n\n"
        "You are a receptionist agent. "
        "First, ask the user for their phone number and check using check_patients_exist tool. "
        "If the phone number exists, greet the user. "
        "If not, use insert_patient to collect name, email, and phone number, and save them into the database. "
        "If the user wants to update name, email, or phone number, use update_patient_records tool. "
        "Once a patient is registered or verified and you have their patient_id:\n"
        "- MANDATORY ROUTING FOR APPOINTMENTS & PAYMENT PREFERENCE: For doctors, specializations, slots, or booking/viewing/rescheduling/canceling appointments — AND whenever the patient answers a payment preference question (such as 'right away', 'now', 'pay now', 'pay online', 'after that', 'later', 'at the clinic' during booking) — you MUST call handoff_to_appointment_agent with their patient_id and full request details. DO NOT call billing agent during a booking in progress!\n"
        "- ONLY call handoff_to_billing if the user explicitly asks to check the payment status of an already-booked past appointment (e.g. 'is my payment done?', 'payment status') or asks for an invoice for a completed visit.\n"
        "- For checking insurance coverage, eligibility, or copays (or if the user asks to BOTH check insurance and get a bill), "
        "IMMEDIATELY call handoff_to_insurance with their patient_id and full request details (include appointment_id and service_code if mentioned).\n"
        "IMPORTANT: All handoff tools are synchronous tool calls that return the complete answer. "
        "When a handoff tool returns, relay its message directly to the user. "
        "When the user asks to know doctors, departments, or specializations, you MUST display the actual doctors and their departments. NEVER give a generic response without showing the doctors! "
        "CRITICAL PAYMENT LINK MANDATE: If any tool response contains a payment link or URL (such as https://checkout.stripe.com/...), "
        "you MUST include the complete, exact payment URL in your final message to the user. "
        "NEVER omit the payment URL, and NEVER say 'sent via SMS' without showing the full clickable payment link directly in your response! "
        "Never call more than one tool in a single turn. "
        "Never share the details of another person via a mobile number."
    ),
    tools=[
        check_patients_exist,
        insert_patient,
        update_patient_records,
        handoff_to_appointment_agent,
        handful_to_appointment_agent,
        _get_handoff_to_insurance(),
        _get_handoff_to_billing(),
    ],
    checkpointer=checkpointer,
)


class SafeReceptionistAgent:
    """Wrapper that guarantees:
    1. Any Stripe payment URL generated in a turn is preserved in the final message.
    2. Any doctor lists, slots, or handoff details are never dropped or truncated by the router.
    """

    def __init__(self, raw_agent):
        self._raw_agent = raw_agent

    def invoke(self, *args, **kwargs):
        res = self._raw_agent.invoke(*args, **kwargs)
        if isinstance(res, dict) and "messages" in res and res["messages"]:
            last_msg = res["messages"][-1]
            last_content = getattr(last_msg, "content", "") or ""

            # Check if a handoff tool was executed in this turn
            handoff_content = None
            for m in reversed(res["messages"][:-1]):
                m_name = getattr(m, "name", "") or ""
                if m_name in (
                    "handoff_to_appointment_agent",
                    "handful_to_appointment_agent",
                    "handoff_to_insurance",
                    "handoff_to_billing",
                ):
                    handoff_content = getattr(m, "content", "")
                    break

            # If the receptionist LLM dropped the full list/content (e.g. only gave a short generic 1-liner),
            # restore the complete handoff answer
            if handoff_content and len(handoff_content.strip()) > len(last_content.strip()) * 2:
                last_content = handoff_content
                last_msg.content = handoff_content

            # Guarantee Stripe URL presence
            stripe_url = None
            for m in reversed(res["messages"]):
                content_str = str(getattr(m, "content", "") or "")
                match = re.search(r"https://checkout\.stripe\.com[^\s\)\"'>]+", content_str)
                if match:
                    stripe_url = match.group(0)
                    break
            if stripe_url and stripe_url not in last_content:
                last_msg.content = f"{last_content}\n\n👉 **Payment Link:** {stripe_url}"
        return res

    def __getattr__(self, name):
        return getattr(self._raw_agent, name)


receptionist_agent = SafeReceptionistAgent(_raw_receptionist_agent)


thread_config = {"configurable": {"thread_id": "session1234"}}
