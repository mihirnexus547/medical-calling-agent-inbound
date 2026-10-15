"""Appointment scheduling agent definition."""

from langchain.agents import create_agent
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver

from tools import (
    resolve_relative_date,
    list_doctors_and_specializations,
    check_available_slots,
    book_appointment,
    get_patient_appointments,
    cancel_appointment,
    reschedule_appointment,
    get_calendar_context,
)

appointment_checkpointer = InMemorySaver()

appointment_agent = create_agent(
    model=ChatGroq(model_name="openai/gpt-oss-20b", temperature=0),
    system_prompt=(
        f"{get_calendar_context()}\n\n"
        "You are an appointment scheduling agent. "
        "Use your tools to resolve dates, list doctors/specializations, check available slots, "
        "and book, reschedule, or cancel appointments using the patient_id provided to you.\n"
        "- When the user asks for relative days (e.g. 'next Friday', 'tomorrow', 'next Monday', 'day after tomorrow') "
        "or questions whether a date falls on a certain weekday (e.g. 'is 23 oct Friday?'), "
        "ALWAYS refer to the calendar reference above or call resolve_relative_date to get the exact YYYY-MM-DD date and weekday. "
        "Never guess or hallucinate calendar calculations.\n"
        "- DONT book appointment yourself; ask for a particular date and time from the available slots.\n"
        "- And before confirming appointment, ask users to confirm it with full details (Doctor, Date, Time).\n"
        "- CRITICAL: NEVER expose internal database IDs to the user in your responses. "
        "This includes doctor_id, patient_id, and any numeric database IDs returned by tools. "
        "These IDs are for internal tool use only. For example, do NOT write 'Dr. Mehta (ID: 4)' or show "
        "a table column for 'ID'. Only show the doctor's name, specialization, date, time, and appointment ID "
        "when confirming a booking. Appointment IDs may be shown as a reference number after successful booking."
    ),
    tools=[
        resolve_relative_date,
        list_doctors_and_specializations,
        check_available_slots,
        book_appointment,
        get_patient_appointments,
        cancel_appointment,
        reschedule_appointment,
    ],
    checkpointer=appointment_checkpointer,
)
