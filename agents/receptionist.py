"""Receptionist agent definition (includes the handoff tool to appointment agent)."""

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
    # Import here to avoid circular imports (appointment_agent imports tools which imports config)
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


checkpointer = InMemorySaver()

receptionist_agent = create_agent(
    model=ChatGroq(model_name="openai/gpt-oss-20b", temperature=0),
    system_prompt=(
        f"{get_calendar_context()}\n\n"
        "You are a receptionist agent. "
        "First, ask the user for their phone number and check using check_patients_exist tool. "
        "If the phone number exists, greet the user. "
        "If not, use insert_patient to collect name, email, and phone number, and save them into the database. "
        "If the user wants to update name, email, or phone number, use update_patient_records tool. "
        "Once a patient is registered or verified and you have their patient_id, if they ask about doctors, "
        "available specializations, available slots, or booking, viewing, rescheduling, or canceling an appointment, "
        "IMMEDIATELY call handoff_to_appointment_agent with their patient_id and full request details. "
        "IMPORTANT: handoff_to_appointment_agent is a synchronous tool call - it runs the appointment agent and returns "
        "the complete answer right now. Do NOT say things like 'I have forwarded your request' or "
        "'our specialist will reach out'. Simply relay the tool's returned response directly to the user. "
        "Never share the details of another person via a mobile number."
    ),
    tools=[check_patients_exist, insert_patient, update_patient_records, handoff_to_appointment_agent],
    checkpointer=checkpointer,
)

thread_config = {"configurable": {"thread_id": "session1234"}}
