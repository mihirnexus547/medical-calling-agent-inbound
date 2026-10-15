from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_groq import ChatGroq
from dotenv import load_dotenv
import psycopg2
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field 
from typing import Optional
import os
import logging
import time 
import sys 
from logging.handlers import RotatingFileHandler
from datetime import datetime, date, timedelta
import calendar
import re

from langchain_core.callbacks import BaseCallbackHandler

log_format = (
    "%(asctime)s|%(levelname)s|%(name)s|%(message)s"
)

#Write logs to a rotating file and terminal 
file_handler = RotatingFileHandler(
    "receptionist.log",
    maxBytes=5*1024*1024,
    backupCount=3,
    encoding="utf-8",
)

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        file_handler,
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("mca.receptionist")


load_dotenv()

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_PROJECT"] = "mca_multiagent_inbound"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"

class UpdatePatientInput(BaseModel):
    patient_id: str = Field(description="The unique database ID or phone number of the patient.")
    name: Optional[str] = Field(default=None, description="The new full name of the patient")
    email: Optional[str] = Field(default=None, description="The new email address of the patient")
    phone: Optional[str] = Field(default=None, description="The new phone number of the patient")



conn = psycopg2.connect(
    dbname = "patient_db",
    user = "postgres",
    password="postgres",
    host="localhost",
    port="5432"
)

cursor = conn.cursor()




@tool
def check_patients_exist(phone_number: str) -> str:
    """Check whether a patient exists by phone number."""

    start_time = time.perf_counter()
    logger.info("Patient lookup started: phone_number=%s", phone_number)

    cleaned = "".join(filter(str.isdigit, phone_number))

    query = """
        SELECT id, name, email, phone
        FROM patients
        WHERE phone = %s
           OR RIGHT(
               REGEXP_REPLACE(phone, '[^0-9]', '', 'g'), 10
           ) = RIGHT(%s, 10)
        LIMIT 1;
    """

    try:
        cursor.execute(query, (cleaned, cleaned))
        result = cursor.fetchone()

        duration = time.perf_counter() - start_time

        if result:
            logger.info(
                "Patient lookup completed: found=true patient_id=%s duration=%.3fs",
                result[0],
                duration,
            )
            return (
                f"Patient found: ID: {result[0]}, "
                f"Name: {result[1]}, Email: {result[2]}, "
                f"Phone: {result[3]}"
            )

        logger.info(
            "Patient lookup completed: found=false duration=%.3fs",
            duration,
        )
        return "Patient not found."

    except Exception:
        conn.rollback()
        duration = time.perf_counter() - start_time
        logger.exception(
            "Patient lookup failed: phone_number=%s duration=%.3fs",
            phone_number,
            duration,
        )
        return "Patient lookup failed. Please try again."



@tool
def insert_patient(name: str, email: str, phone: str) -> str:
    """Register a new patient in the database."""

    start_time = time.perf_counter()
    logger.info("Patient registration started: name=%s, email=%s, phone=%s", name, email, phone)

    query = """
        INSERT INTO patients (name, email, phone)
        VALUES (%s, %s, %s)
        RETURNING id;
    """

    try:
        cursor.execute(query, (name, email, phone))
        patient_id = cursor.fetchone()[0]
        conn.commit()

        duration = time.perf_counter() - start_time

        logger.info(
            "Patient registration succeeded: "
            "patient_id=%s duration=%.3fs",
            patient_id,
            duration,
        )

        return f"Patient registered successfully.ID:{patient_id}"

    except Exception:
        conn.rollback()

        duration = time.perf_counter() - start_time

        logger.exception(
            "Patient registration failed: name=%s phone=%s duration=%.3fs",
            name,
            phone,
            duration,
        )

        return "Patient registration failed. Please try again."



@tool(args_schema=UpdatePatientInput)
def update_patient_records(
    patient_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
) -> str:
    """
    Update explicitly requested patient profile fields.
    """

    start_time = time.perf_counter()
    updates = {
        key: value
        for key, value in {
            "name": name,
            "email": email,
            "phone": phone,
        }.items()
        if value is not None
    }
    logger.info(
        "Patient update started: patient_id=%s, fields=%s",
        patient_id,
        list(updates.keys()) if updates else "none",
    )

    if not updates:
        duration = time.perf_counter() - start_time

        logger.warning(
            "Patient update rejected: no fields supplied, patient_id=%s duration=%.3fs",
            patient_id,
            duration,
        )

        return "No updates were specified."

    try:
        cleaned_id = "".join(
            filter(str.isdigit, str(patient_id))
        )

        # Determine whether the identifier is a database ID
        # or a phone number using the existing convention.
        if (
            cleaned_id.isdigit()
            and int(cleaned_id) <= 2147483647
            and len(cleaned_id) < 10
        ):
            where_clause = "id = %(target_id)s"
            target_val = int(cleaned_id)
        else:
            where_clause = """
                RIGHT(
                    REGEXP_REPLACE(phone, '[^0-9]', '', 'g'),
                    10
                ) = RIGHT(%(target_val_str)s, 10)
            """
            target_val = cleaned_id

        set_clause = ", ".join(
            f"{column} = %({column})s"
            for column in updates
        )

        query = f"""
            UPDATE patients
            SET {set_clause}
            WHERE {where_clause}
            RETURNING id;
        """

        query_params = {
            **updates,
            "target_id": target_val,
            "target_val_str": str(target_val),
        }

        cursor.execute(query, query_params)
        updated_patient = cursor.fetchone()

        if updated_patient is None:
            conn.commit()

            duration = time.perf_counter() - start_time

            logger.warning(
                "Patient update found no matching record: patient_id=%s duration=%.3fs",
                patient_id,
                duration,
            )

            return "No matching patient was found."

        conn.commit()

        duration = time.perf_counter() - start_time

        logger.info(
            "Patient update succeeded: patient_id=%s fields=%s duration=%.3fs",
            patient_id,
            ",".join(updates.keys()),
            duration,
        )

        return "Patient information updated successfully."

    except Exception:
        conn.rollback()

        duration = time.perf_counter() - start_time

        logger.exception(
            "Patient update failed: patient_id=%s duration=%.3fs",
            patient_id,
            duration,
        )

        return "Patient update failed. Please try again."




class AgentLoggingCallback(BaseCallbackHandler):
    def on_tool_start(
        self, serialized, input_str, **kwargs
    ):
        tool_name = serialized.get("name", "unknown")
        logger.info("Tool started: %s | input: %s", tool_name, input_str)

    def on_tool_end(self, output, **kwargs):
        output_str = str(output)
        if len(output_str) > 300:
            output_str = output_str[:300] + "... (truncated)"
        logger.info("Tool completed: output=%s", output_str)

    def on_tool_error(self, error, **kwargs):
        logger.error(
            "Tool failed: %s: %s",
            type(error).__name__,
            error,
        )

    def on_llm_start(
        self, serialized, prompts, **kwargs
    ):
        logger.info("LLM call started")

    def on_llm_end(self, response, **kwargs):
        logger.info("LLM call completed")

    def on_llm_error(self, error, **kwargs):
        logger.error(
            "LLM call failed: %s: %s",
            type(error).__name__,
            error,
        )




def resolve_date_helper(expr: str):
    """
    Resolve relative date descriptions or date strings into a (datetime.date, weekday_name) tuple.
    Returns (None, None) if expression cannot be parsed.
    """
    if not expr:
        return None, None

    today = date.today()
    clean = str(expr).strip().lower()

    if clean in ["today"]:
        return today, today.strftime("%A")
    if clean in ["tomorrow"]:
        d = today + timedelta(days=1)
        return d, d.strftime("%A")
    if clean in ["day after tomorrow"]:
        d = today + timedelta(days=2)
        return d, d.strftime("%A")

    m = re.match(r"in\s+(\d+)\s+days?", clean)
    if m:
        d = today + timedelta(days=int(m.group(1)))
        return d, d.strftime("%A")

    weekdays = {name.lower(): idx for idx, name in enumerate(calendar.day_name)}
    matched_weekday = None
    for name, idx in weekdays.items():
        if re.search(r"\b" + name + r"\b", clean):
            matched_weekday = idx
            break

    if matched_weekday is not None:
        today_weekday = today.weekday()
        days_ahead = (matched_weekday - today_weekday) % 7
        if days_ahead == 0:
            days_ahead = 7

        if "next" in clean:
            # If target weekday is still ahead this week (e.g., today is Thursday, asking for Friday),
            # 'next Friday' refers to Friday of the next week (+7 days).
            if days_ahead < 7 and matched_weekday > today_weekday:
                days_ahead += 7

        d = today + timedelta(days=days_ahead)
        return d, d.strftime("%A")

    clean_date = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", clean)
    for fmt in [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
        "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y",
        "%d %b", "%d %B", "%b %d", "%B %d",
    ]:
        try:
            parsed = datetime.strptime(clean_date, fmt).date()
            if parsed.year == 1900:
                parsed = parsed.replace(year=today.year)
            return parsed, parsed.strftime("%A")
        except ValueError:
            pass

    return None, None


def get_calendar_context() -> str:
    """Generate dynamic calendar context for the upcoming 14 days."""
    today = date.today()
    lines = [
        f"CALENDAR & DATE REFERENCE (Today is {today.strftime('%A, %Y-%m-%d')}):",
        "Upcoming 14-day calendar:",
    ]
    for i in range(15):
        d = today + timedelta(days=i)
        day_name = d.strftime('%A')
        qualifier = ""
        if i == 0:
            qualifier = " [Today]"
        elif i == 1:
            qualifier = f" [Tomorrow / This {day_name}]"
        elif i <= 6:
            qualifier = f" [This {day_name}]"
        elif i == 7:
            qualifier = " [Next week same day]"
        elif i <= 13:
            qualifier = f" [Next {day_name}]"
        lines.append(f"  - {d.strftime('%Y-%m-%d')}: {day_name}{qualifier}")
    lines.append(
        "CRITICAL INSTRUCTION: When the user mentions any relative date (e.g. 'next Friday', 'tomorrow', 'this Monday', 'Oct 23'), "
        "ALWAYS check the calendar reference above or call the resolve_relative_date tool. Never hallucinate day-of-week mappings. "
        "For example, if today is Thursday Oct 15, tomorrow is Friday Oct 16, and 'next Friday' is Friday Oct 23."
    )
    return "\n".join(lines)


@tool
def resolve_relative_date(query: str) -> str:
    """Resolve any relative date expression (e.g. 'today', 'tomorrow', 'this friday', 'next friday', 'next monday', or '23 oct 2026') to the exact YYYY-MM-DD date and corresponding weekday."""
    start_time = time.perf_counter()
    logger.info("Resolving relative date started: query=%s", query)

    resolved_date, day_name = resolve_date_helper(query)
    duration = time.perf_counter() - start_time

    if resolved_date:
        res = f"{resolved_date.isoformat()} ({day_name})"
        logger.info(
            "Resolving relative date completed: query=%s result=%s duration=%.3fs",
            query,
            res,
            duration,
        )
        return f"Date: {resolved_date.isoformat()} ({day_name})"

    logger.warning(
        "Resolving relative date could not parse: query=%s duration=%.3fs",
        query,
        duration,
    )
    today = date.today()
    return f"Could not determine date for '{query}'. Note: Today is {today.strftime('%A, %Y-%m-%d')}."


@tool
def check_available_slots(doctor_name: str, available_date: str) -> str:
    """Find available time slots for a doctor by name and date(YYYY-MM-DD or relative like 'next friday')."""
    start_time = time.perf_counter()
    logger.info(
        "Checking available slots started: doctor_name=%s, available_date=%s",
        doctor_name,
        available_date,
    )

    resolved_date, weekday_name = resolve_date_helper(available_date)
    query_date = resolved_date.isoformat() if resolved_date else available_date
    date_display = f"{weekday_name}, {query_date}" if weekday_name else query_date

    query = """
        SELECT d.id, d.name, d.specialization, da.slot_time
        FROM doctors d 
        JOIN doctor_availability da ON d.id = da.doctor_id
        WHERE d.name ILIKE %s
            AND da.available_date = %s
            AND da.is_booked = FALSE
         ORDER BY da.slot_time;
    """

    try:
        cursor.execute(query, (f"%{doctor_name}%", query_date))
        rows = cursor.fetchall()
        duration = time.perf_counter() - start_time

        if not rows:
            logger.info(
                "Checking available slots completed: found=false doctor=%s date=%s duration=%.3fs",
                doctor_name,
                query_date,
                duration,
            )
            return f"No open slots found for {doctor_name} on {date_display}"

        doc_id, doc_name, spec, _ = rows[0]
        slots = [str(row[3]) for row in rows]

        logger.info(
            "Checking available slots completed: found=true doctor=%s (ID:%s) slots_count=%d duration=%.3fs",
            doc_name,
            doc_id,
            len(slots),
            duration,
        )
        return f"Doctor:{doc_name} (ID:{doc_id},{spec}) | Open slots on {date_display}:{','.join(slots)}"

    except Exception:
        conn.rollback()
        duration = time.perf_counter() - start_time
        logger.exception(
            "Checking available slots failed: doctor=%s date=%s duration=%.3fs",
            doctor_name,
            query_date,
            duration,
        )
        return f"Failed to check available slots for {doctor_name}. Please try again."


@tool 
def book_appointment(patient_id: int, doctor_id: int, appointment_date: str, appointment_time: str) -> str:
    """Book an open slot for a registered patient and mark the slot as booked"""
    start_time = time.perf_counter()
    logger.info(
        "Appointment booking started: patient_id=%s, doctor_id=%s, date=%s, time=%s",
        patient_id,
        doctor_id,
        appointment_date,
        appointment_time,
    )

    try:
        # Mark slot as booked only if it is currently open (is_booked = FALSE)
        update_slot = """
            UPDATE doctor_availability
            SET is_booked = TRUE
            WHERE doctor_id = %s AND available_date = %s
            AND slot_time = %s AND is_booked = FALSE
            RETURNING id;
        """

        cursor.execute(update_slot, (doctor_id, appointment_date, appointment_time))
        if not cursor.fetchone():
            conn.rollback()
            duration = time.perf_counter() - start_time
            logger.warning(
                "Appointment booking rejected: slot unavailable or invalid "
                "doctor_id=%s date=%s time=%s duration=%.3fs",
                doctor_id,
                appointment_date,
                appointment_time,
                duration,
            )
            return "The slot is either invalid or already booked"

        # Insert the appointment record 
        insert_appt = """
                INSERT INTO appointments(patient_id, doctor_id, appointment_date, appointment_time, status)
                VALUES (%s, %s, %s, %s, 'booked')
                RETURNING id;
        """

        cursor.execute(insert_appt, (patient_id, doctor_id, appointment_date, appointment_time))
        appt_id = cursor.fetchone()[0]
        conn.commit()

        duration = time.perf_counter() - start_time
        logger.info(
            "Appointment booking succeeded: appointment_id=%s patient_id=%s doctor_id=%s duration=%.3fs",
            appt_id,
            patient_id,
            doctor_id,
            duration,
        )
        return f"Appointment booked! Appointment ID:{appt_id}"

    except Exception:
        conn.rollback()
        duration = time.perf_counter() - start_time
        logger.exception(
            "Appointment booking failed: patient_id=%s doctor_id=%s date=%s time=%s duration=%.3fs",
            patient_id,
            doctor_id,
            appointment_date,
            appointment_time,
            duration,
        )
        return "Failed to book appointment. Please try again."


@tool 
def list_doctors_and_specializations(specialization: Optional[str] = None) -> str:
    """List available specializations, or find doctors for a specific specialization."""
    start_time = time.perf_counter()
    logger.info(
        "List doctors/specializations started: specialization=%s",
        specialization,
    )

    try:
        if not specialization:
            # DISTINCT prevents duplicate specialization names
            all_specialization_query = "SELECT DISTINCT specialization FROM doctors;"
            cursor.execute(all_specialization_query)
            rows = cursor.fetchall()
            specialization_names = ",".join(row[0] for row in rows)
            duration = time.perf_counter() - start_time
            logger.info(
                "List specializations completed: count=%d duration=%.3fs",
                len(rows),
                duration,
            )
            return f"Specializations available:{specialization_names}"
        else:
            specific_specialization_query = """
                SELECT id, name FROM doctors WHERE specialization ILIKE %s;
            """
            cursor.execute(specific_specialization_query, (f"%{specialization}%",))
            rows = cursor.fetchall()
            duration = time.perf_counter() - start_time

            if not rows:
                logger.info(
                    "List doctors completed: none found for specialization=%s duration=%.3fs",
                    specialization,
                    duration,
                )
                return f"No doctors found for specialization:{specialization}"

            doctors_list = ",".join(f"{row[1]} (ID:{row[0]})" for row in rows)
            logger.info(
                "List doctors completed: specialization=%s count=%d duration=%.3fs",
                specialization,
                len(rows),
                duration,
            )
            return f"Specialization {specialization} doctors available:{doctors_list}"

    except Exception:
        conn.rollback()
        duration = time.perf_counter() - start_time
        logger.exception(
            "List doctors and specializations failed: specialization=%s duration=%.3fs",
            specialization,
            duration,
        )
        return "Failed to fetch doctors and specializations"
@tool 
def get_patient_appointments(patient_id: int) -> str:
    """Fetch all active booked appointments for a specific patient"""
    start_time = time.perf_counter()
    logger.info("Fetching patient appointments started: patient_id=%s", patient_id)

    query = """
            SELECT a.id, a.appointment_date, a.appointment_time, d.name, d.specialization
            FROM appointments AS a 
            JOIN doctors AS d ON a.doctor_id = d.id
            WHERE a.status = 'booked' AND a.patient_id=%s
            ORDER BY a.appointment_date, a.appointment_time;
    """
    try:
        cursor.execute(query, (patient_id,))
        rows = cursor.fetchall()
        duration = time.perf_counter() - start_time

        if not rows:
            logger.info(
                "Fetching patient appointments completed: none found for patient_id=%s duration=%.3fs",
                patient_id,
                duration,
            )
            return f"No active appointments found for patient ID {patient_id}."
        
        appt_list = [
            f"Appointment ID:{row[0]} | Date:{row[1]} | Time:{row[2]} | Doctor:{row[3]} ({row[4]})"
            for row in rows
        ]
        logger.info(
            "Fetching patient appointments completed: patient_id=%s count=%d duration=%.3fs",
            patient_id,
            len(rows),
            duration,
        )
        return "Active Appointments:\n" + "\n".join(appt_list)
    except Exception:
        conn.rollback()
        duration = time.perf_counter() - start_time
        logger.exception(
            "Fetching patient appointments failed: patient_id=%s duration=%.3fs",
            patient_id,
            duration,
        )
        return "Failed to fetch patient appointments."

@tool
def cancel_appointment(patient_id: int, appointment_date: str) -> str:
    """Cancel an active appointment for a patient on a given date (YYYY-MM-DD)."""
    start_time = time.perf_counter()
    logger.info(
        "Cancelling appointment started: patient_id=%s, appointment_date=%s",
        patient_id,
        appointment_date,
    )
    try:
        # find the appointment to get the doctor_id and appointment_time
        find_appt_query = """
            SELECT id, doctor_id, appointment_time
            FROM appointments
            WHERE patient_id = %s AND appointment_date = %s AND status = 'booked';
        """
        cursor.execute(find_appt_query, (patient_id, appointment_date))
        appointment = cursor.fetchone()
        
        if not appointment:
            duration = time.perf_counter() - start_time
            logger.warning(
                "Cancelling appointment failed: no active appointment for patient_id=%s date=%s duration=%.3fs",
                patient_id,
                appointment_date,
                duration,
            )
            return f"No active appointment found for patient id:{patient_id} on {appointment_date}."
        
        appt_id, doctor_id, appt_time = appointment

        # update appointment status to cancelled 
        update_apt = """
            UPDATE appointments
            SET status='cancelled'
            WHERE id = %s;
        """
        cursor.execute(update_apt, (appt_id,))
        
        # Free up the slot in doctor_availability
        free_slot = """
            UPDATE doctor_availability
            SET is_booked = FALSE
            WHERE doctor_id = %s AND available_date = %s AND slot_time = %s;
        """
        cursor.execute(free_slot, (doctor_id, appointment_date, appt_time))
        conn.commit()

        duration = time.perf_counter() - start_time
        logger.info(
            "Cancelling appointment succeeded: appointment_id=%s patient_id=%s date=%s time=%s duration=%.3fs",
            appt_id,
            patient_id,
            appointment_date,
            appt_time,
            duration,
        )
        return f"Appointment on {appointment_date} at {appt_time} has been successfully cancelled."
    
    except Exception:
        conn.rollback()
        duration = time.perf_counter() - start_time
        logger.exception(
            "Cancelling appointment failed: patient_id=%s date=%s duration=%.3fs",
            patient_id,
            appointment_date,
            duration,
        )
        return "Failed to cancel appointment. Please try again."

@tool
def reschedule_appointment(patient_id: int, appointment_id: int, new_date: str, new_time: str) -> str:
    """Reschedule an existing appointment to a new date (YYYY-MM-DD) and time (HH:MM)."""
    start_time = time.perf_counter()
    logger.info(
        "Rescheduling appointment started: patient_id=%s, appointment_id=%s, new_date=%s, new_time=%s",
        patient_id,
        appointment_id,
        new_date,
        new_time,
    )
    try:
        # Fetch existing active appointment details 
        cursor.execute(
            """
            SELECT doctor_id, appointment_date, appointment_time
            FROM appointments
            WHERE id = %s AND patient_id = %s AND status='booked';
            """,
            (appointment_id, patient_id),
        )
        current_apt = cursor.fetchone()
        if not current_apt:
            duration = time.perf_counter() - start_time
            logger.warning(
                "Rescheduling appointment rejected: no active appointment found id=%s patient_id=%s duration=%.3fs",
                appointment_id,
                patient_id,
                duration,
            )
            return f"No active appointment found with ID {appointment_id} for patient {patient_id}."
        
        doctor_id, old_date, old_time = current_apt

        # Try to claim the NEW slot first
        cursor.execute(
            """
            UPDATE doctor_availability
            SET is_booked = TRUE
            WHERE doctor_id = %s AND available_date = %s
            AND slot_time = %s AND is_booked = FALSE
            RETURNING id;
            """,
            (doctor_id, new_date, new_time),
        )
        if not cursor.fetchone():
            conn.rollback()
            duration = time.perf_counter() - start_time
            logger.warning(
                "Rescheduling appointment rejected: new slot unavailable doctor_id=%s date=%s time=%s duration=%.3fs",
                doctor_id,
                new_date,
                new_time,
                duration,
            )
            return f"The new slot on {new_date} at {new_time} is not available."
        
        # Free the OLD slot
        cursor.execute(
            """
            UPDATE doctor_availability
            SET is_booked = FALSE
            WHERE doctor_id = %s AND available_date = %s AND slot_time = %s;
            """,
            (doctor_id, old_date, old_time),
        )
        cursor.execute(
            """
            UPDATE appointments 
            SET appointment_date = %s, appointment_time = %s
            WHERE id = %s;
            """,
            (new_date, new_time, appointment_id),
        )
        conn.commit()

        duration = time.perf_counter() - start_time
        logger.info(
            "Rescheduling appointment succeeded: appointment_id=%s patient_id=%s new_date=%s new_time=%s duration=%.3fs",
            appointment_id,
            patient_id,
            new_date,
            new_time,
            duration,
        )
        return f"Appointment {appointment_id} rescheduled to {new_date} at {new_time}."
    except Exception:
        conn.rollback()
        duration = time.perf_counter() - start_time
        logger.exception(
            "Rescheduling appointment failed: appointment_id=%s patient_id=%s duration=%.3fs",
            appointment_id,
            patient_id,
            duration,
        )
        return "Failed to reschedule appointment. Please try again."


@tool 
def handoff_to_appointment_agent(patient_id: int, request_details: str) -> str:
    """Synchronously invoke the Appointment Agent and return its response directly to the user. Use this for ALL doctor lookups, slot checks, booking, rescheduling, canceling, and viewing appointments. The response from this tool IS the answer - relay it verbatim to the user without adding any commentary."""
    start_time = time.perf_counter()
    logger.info(
        "Handoff to Appointment Agent started: patient_id=%s, request_details=%s",
        patient_id,
        request_details,
    )

    try:
        # Use a patient-specific thread_id so the Appointment Agent remembers past turns for this patient 
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
                        "content": f"[System Date: Today is {today_str}] Patient ID:{patient_id}, Request:{request_details}",
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


agent = create_agent(
    model = ChatGroq(model_name = "openai/gpt-oss-20b", temperature = 0),
    system_prompt = (
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
    tools = [check_patients_exist, insert_patient, update_patient_records, handoff_to_appointment_agent],
    checkpointer = checkpointer
)

thread_config = {"configurable":{"thread_id":"session1234"}}


appointment_checkpointer = InMemorySaver()



appointment_agent = create_agent(
    model = ChatGroq(model_name="openai/gpt-oss-20b", temperature=0),
    system_prompt = (
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
    tools = [
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









if __name__ == "__main__":
    logger.info("Receptionist agent initialized")
    print("Receptionist & Appointment system initialized. Type 'exit' to quit.\n")

    while True:
        user_input = input("User: ")

        if user_input.strip().lower() in ["exit", "quit"]:
            logger.info("Receptionist session ended")
            break

        start_time = time.perf_counter()
        logger.info("Agent request started")

        try:
            response = agent.invoke(
                {
                    "messages": [
                        {"role": "user", "content": user_input}
                    ]
                },
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