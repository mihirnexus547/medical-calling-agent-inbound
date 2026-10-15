"""Patient management tools: lookup, registration, and profile updates."""

import time
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import logger, conn, cursor


class UpdatePatientInput(BaseModel):
    patient_id: str = Field(description="The unique database ID or phone number of the patient.")
    name: Optional[str] = Field(default=None, description="The new full name of the patient")
    email: Optional[str] = Field(default=None, description="The new email address of the patient")
    phone: Optional[str] = Field(default=None, description="The new phone number of the patient")


@tool
def check_patients_exist(phone_number: str) -> str:
    """Check whether a patient exists by phone number."""
    start_time = time.perf_counter()
    logger.info("Patient lookup started: phone=%s", phone_number)

    try:
        query = """
            SELECT id, name, email, phone
            FROM patients
            WHERE RIGHT(
                REGEXP_REPLACE(phone, '[^0-9]', '', 'g'),
                10
            ) = RIGHT(
                REGEXP_REPLACE(%s, '[^0-9]', '', 'g'),
                10
            );
        """
        cursor.execute(query, (phone_number,))
        result = cursor.fetchone()
        duration = time.perf_counter() - start_time

        if result:
            patient_id, name, email, phone = result
            logger.info(
                "Patient lookup succeeded: found=true patient_id=%s duration=%.3fs",
                patient_id,
                duration,
            )
            return (
                f"Patient found: ID:{patient_id}, Name:{name}, "
                f"Email:{email}, Phone:{phone}"
            )

        logger.info(
            "Patient lookup succeeded: found=false duration=%.3fs",
            duration,
        )
        return "Patient not found."

    except Exception:
        conn.rollback()
        duration = time.perf_counter() - start_time
        logger.exception(
            "Patient lookup failed: phone=%s duration=%.3fs",
            phone_number,
            duration,
        )
        return "Patient lookup failed. Please try again."


@tool
def insert_patient(name: str, email: str, phone: str) -> str:
    """Register a new patient with name, email, and phone number."""
    start_time = time.perf_counter()
    logger.info("Patient registration started: name=%s phone=%s", name, phone)

    try:
        cursor.execute(
            "INSERT INTO patients (name, email, phone) VALUES (%s, %s, %s) RETURNING id;",
            (name, email, phone),
        )
        patient_id = cursor.fetchone()[0]
        conn.commit()
        duration = time.perf_counter() - start_time
        logger.info(
            "Patient registration succeeded: patient_id=%s name=%s duration=%.3fs",
            patient_id,
            name,
            duration,
        )
        return f"Patient registered successfully. Patient ID: {patient_id}"

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
    """Update explicitly requested patient profile fields."""
    start_time = time.perf_counter()
    updates = {
        key: value
        for key, value in {"name": name, "email": email, "phone": phone}.items()
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
        cleaned_id = "".join(filter(str.isdigit, str(patient_id)))

        if cleaned_id.isdigit() and int(cleaned_id) <= 2147483647 and len(cleaned_id) < 10:
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

        set_clause = ", ".join(f"{col} = %({col})s" for col in updates)
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
