"""Appointment management tools: list doctors, check slots, book, view, cancel, reschedule."""

import time
from typing import Optional

from langchain_core.tools import tool

from config import logger, conn, cursor
from tools.date_utils import resolve_date_helper


@tool
def list_doctors_and_specializations(specialization: Optional[str] = None) -> str:
    """List available specializations, or find doctors for a specific specialization."""
    start_time = time.perf_counter()
    logger.info("List doctors/specializations started: specialization=%s", specialization)

    try:
        if not specialization:
            cursor.execute("SELECT DISTINCT specialization FROM doctors;")
            rows = cursor.fetchall()
            specialization_names = ",".join(row[0] for row in rows)
            duration = time.perf_counter() - start_time
            logger.info(
                "List specializations completed: count=%d duration=%.3fs",
                len(rows),
                duration,
            )
            return f"Specializations available:{specialization_names}"

        cursor.execute(
            "SELECT id, name FROM doctors WHERE specialization ILIKE %s;",
            (f"%{specialization}%",),
        )
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
def check_available_slots(doctor_name: str, available_date: str) -> str:
    """Find available time slots for a doctor by name and date (YYYY-MM-DD or relative like 'next friday')."""
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
def book_appointment(
    patient_id: int,
    doctor_id: int,
    appointment_date: str,
    appointment_time: str,
) -> str:
    """Book an open slot for a registered patient and mark the slot as booked."""
    start_time = time.perf_counter()
    logger.info(
        "Appointment booking started: patient_id=%s, doctor_id=%s, date=%s, time=%s",
        patient_id,
        doctor_id,
        appointment_date,
        appointment_time,
    )

    try:
        cursor.execute(
            """
            UPDATE doctor_availability
            SET is_booked = TRUE
            WHERE doctor_id = %s AND available_date = %s
              AND slot_time = %s AND is_booked = FALSE
            RETURNING id;
            """,
            (doctor_id, appointment_date, appointment_time),
        )
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

        cursor.execute(
            """
            INSERT INTO appointments(patient_id, doctor_id, appointment_date, appointment_time, status)
            VALUES (%s, %s, %s, %s, 'booked')
            RETURNING id;
            """,
            (patient_id, doctor_id, appointment_date, appointment_time),
        )
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
def get_patient_appointments(patient_id: int) -> str:
    """Fetch all active booked appointments for a specific patient."""
    start_time = time.perf_counter()
    logger.info("Fetching patient appointments started: patient_id=%s", patient_id)

    query = """
        SELECT a.id, a.appointment_date, a.appointment_time, d.name, d.specialization
        FROM appointments AS a
        JOIN doctors AS d ON a.doctor_id = d.id
        WHERE a.status = 'booked' AND a.patient_id = %s
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
        cursor.execute(
            """
            SELECT id, doctor_id, appointment_time
            FROM appointments
            WHERE patient_id = %s AND appointment_date = %s AND status = 'booked';
            """,
            (patient_id, appointment_date),
        )
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

        cursor.execute("UPDATE appointments SET status='cancelled' WHERE id = %s;", (appt_id,))
        cursor.execute(
            """
            UPDATE doctor_availability
            SET is_booked = FALSE
            WHERE doctor_id = %s AND available_date = %s AND slot_time = %s;
            """,
            (doctor_id, appointment_date, appt_time),
        )
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
def reschedule_appointment(
    patient_id: int,
    appointment_id: int,
    new_date: str,
    new_time: str,
) -> str:
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

        cursor.execute(
            """
            UPDATE doctor_availability
            SET is_booked = FALSE
            WHERE doctor_id = %s AND available_date = %s AND slot_time = %s;
            """,
            (doctor_id, old_date, old_time),
        )
        cursor.execute(
            "UPDATE appointments SET appointment_date = %s, appointment_time = %s WHERE id = %s;",
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
