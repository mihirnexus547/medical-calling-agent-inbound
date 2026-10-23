"""Insurance eligibility checking tools."""

import time
from langchain_core.tools import tool
from config import logger, conn, cursor


@tool 
def check_insurance_eligibility(patient_id: str, service_code: str, appointment_id: int) -> str:
    """Checks the active insurance policy for a patient and determines the cost breakdown
    (insurer pays vs patient pays) for a given service code and logs the check.
    """
    start_time = time.perf_counter()
    logger.info(
        "Insurance check started: patient_id=%s, service_code=%s, appointment_id=%s",
        patient_id,
        service_code,
        appointment_id,
    )
    try:
        query = """
            SELECT ip.policy_id, sp.price_cents, cr.covered, cr.copay_cents, cr.coinsurance_percent
            FROM insurance_policies ip
            JOIN coverage_rules cr ON ip.plan_id = cr.plan_id
            JOIN service_prices sp ON cr.service_code = sp.service_code
            WHERE ip.patient_id = %s AND ip.is_active = 1 AND sp.service_code = %s;
        """

        cursor.execute(query, (patient_id, service_code))
        result = cursor.fetchone()

        if not result:
            return "No active coverage found. Patient is responsible for the full base price."
        
        policy_id, base_price, covered, copay, coinsurance_percent = result 

        if covered == 0:
            return f"Service {service_code} is explicitly not covered by this plan. Patient pays the full price."
        
        actual_copay = min(copay, base_price)
        patient_amount = actual_copay + ((base_price - actual_copay) * coinsurance_percent // 100)
        insurer_amount = base_price - patient_amount

        insert_query = """
            INSERT INTO insurance_checks
            (appointment_id, policy_id, status, visit_cost_cents, insurer_amount_cents, patient_amount_cents)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING check_id;
        """

        cursor.execute(insert_query, (
            appointment_id, policy_id, 'covered', base_price, insurer_amount, patient_amount
        ))

        check_id = cursor.fetchone()[0]
        conn.commit()

        duration = time.perf_counter() - start_time
        logger.info(
            "Insurance check completed: check_id=%s patient_amount=%s insurer_amount=%s duration=%.3fs",
            check_id,
            patient_amount,
            insurer_amount,
            duration,
        )

        return (
            f"Eligibility confirmed (Check ID:{check_id}). "
            f"Total Cost:{base_price} cents. "
            f"Patient pays:{patient_amount} cents. "
            f"Insurer pays:{insurer_amount} cents."
        )

    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception("Error checking insurance eligibility: %s", e)
        return f"Error Checking eligibility: {str(e)}"
