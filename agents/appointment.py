"""Appointment scheduling agent definition with integrated payment preference flow."""

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
    create_invoice,
    generate_payment_link,
    check_consultation_fee,
)

import os
from dotenv import load_dotenv

load_dotenv()

from agents import get_chat_llm

appointment_checkpointer = InMemorySaver()

appointment_agent = create_agent(
    model=get_chat_llm(temperature=0.1),
    system_prompt=(
        f"{get_calendar_context()}\n\n"
        "You are an appointment scheduling agent. "
        "Use your tools to resolve dates, list doctors/specializations, check available slots, "
        "and book, reschedule, or cancel appointments using the patient_id provided to you.\n"
        "- When the user asks for relative days (e.g. 'next Friday', 'tomorrow', 'next Monday', 'day after tomorrow') "
        "or questions whether a date falls on a certain weekday (e.g. 'is 23 oct Friday?'), "
        "ALWAYS refer to the calendar reference above or call resolve_relative_date to get the exact YYYY-MM-DD date and weekday. "
        "Never guess or hallucinate calendar calculations.\n"
        "- DONT book appointment immediately without user selecting a slot; ask for a particular date and time from the available slots.\n"
        "- MANDATORY APPOINTMENT BOOKING, FEE CONFIRMATION & PAYMENT FLOW:\n"
        "  1. WHEN A PATIENT SELECTS OR ASKS TO BOOK A SLOT:\n"
        "     - Call check_consultation_fee with patient_id and service_code 'CONSULT' to check the fee.\n"
        "     - State the exact fee amount to the patient and ask if they agree to proceed:\n"
        "       'The consultation fee for your appointment with Dr. [Doctor] on [Date] at [Time] is [quote the exact fee from check_consultation_fee, e.g. $50.00 or $150.00]. Would you like to agree to this amount and confirm your booking?'\n"
        "     - DO NOT book the slot until the patient explicitly agrees.\n"
        "  2. IF THE PATIENT AGREES (e.g. 'yes', 'agree', 'proceed', 'sure', 'okay', 'pay now', 'confirm', 'book it'):\n"
        "     - Call book_appointment to book the appointment slot.\n"
        "     - Call create_invoice (service_code 'CONSULT') to generate the invoice.\n"
        "     - Call generate_payment_link with that invoice_id to generate the Stripe payment link.\n"
        "     - Confirm that the appointment is booked with the date, time, and doctor, and ALWAYS provide the full clickable payment link directly in your response:\n"
        "       'Your appointment is confirmed for [Date] at [Time] with Dr. [Doctor]! Please complete your payment here: [paste exact URL returned by generate_payment_link]'\n"
        "     - NEVER omit the payment link and NEVER say 'link sent via SMS' without including the full link right here.\n"
        "  3. IF THE PATIENT DECLINES (e.g. 'no', 'decline', 'too expensive', 'cancel', 'don't want', 'nevermind'):\n"
        "     - If the appointment was already booked or held, call cancel_appointment.\n"
        "     - Inform the patient that the booking is cancelled and ask if they would like to reschedule for a different date/time or consult with another specialist:\n"
        "       'Understood. The appointment has been cancelled. Would you like to reschedule for a different date or time, or consult with another doctor?'\n"
        "  4. IF THE PATIENT ASKS TO RESCHEDULE:\n"
        "     - Call check_available_slots to find open slots for their desired date or doctor.\n"
        "     - Help them select a new slot and proceed with fee confirmation and booking.\n"
        "- CRITICAL: NEVER expose internal database IDs to the user in your responses. "
        "This includes doctor_id, patient_id, and any numeric database IDs returned by tools. "
        "These IDs are for internal tool use only. Only show the doctor's name, specialization, date, time, and appointment ID "
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
        check_consultation_fee,
        create_invoice,
        generate_payment_link,
    ],
    checkpointer=appointment_checkpointer,
)
