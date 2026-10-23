"""
Comprehensive script to populate and synchronize patient_db with realistic records across:
- Doctors & Specializations
- Patients
- Doctor Availability Slots (Next 21 days from today)
- Service Prices (Consult, Follow-up, Specialist, Lab)
- Coverage Rules (Gold, Silver, Bronze plans)
- Insurance Policies
- Appointments (Booked, Cancelled, and Test Cases)
"""

import os
import random
from datetime import datetime, date, time, timedelta
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME", "patient_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Aayush",
    "Krishna", "Ishan", "Shaurya", "Atharv", "Advik", "Pranav", "Advaith",
    "Aryan", "Dhruv", "Kabir", "Ritvik", "Ananya", "Diya", "Gauri", "Ishita",
    "Kavya", "Khushi", "Myra", "Navya", "Pari", "Riya", "Saanvi", "Tanvi",
    "Vanya", "Yashvi", "Aadhya", "Tara", "Meera", "Sneha", "Pooja", "Neha",
    "Rohan", "Kunal", "Rahul", "Vikram", "Sameer", "Amit", "Deepak", "Manish",
    "Suresh", "Rajesh", "Sanjay", "Ankit", "Alok", "Nikhil", "Gaurav", "Varun",
    "Shreya", "Rashi", "Simran", "Divya", "Swati", "Bhavna", "Kiran", "Geeta",
    "Sunita", "Harsh", "Mayank", "Tushar", "Chirag", "Jatin", "Mohit"
]

LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Mehta", "Shah", "Joshi", "Bhatia", "Malhotra",
    "Kapoor", "Khanna", "Reddy", "Nair", "Rao", "Iyer", "Gupta", "Agarwal",
    "Jain", "Saxena", "Mishra", "Pandey", "Choudhary", "Singh", "Yadav",
    "Kumar", "Das", "Banerjee", "Chatterjee", "Mukherjee", "Deshmukh", "Kulkarni"
]

DOCTORS_DATA = [
    ("Dr. Sharma", "Cardiologist"),
    ("Dr. Patel", "Dermatologist"),
    ("Dr. Desail", "General Physician"),
    ("Dr. Rajesh Mehta", "Orthopedic"),
    ("Dr. Priya Nair", "Pediatrician"),
    ("Dr. Ananya Iyer", "Neurologist"),
    ("Dr. Vikram Verma", "Gynecologist"),
    ("Dr. Sunita Rao", "ENT Specialist"),
    ("Dr. Arjun Kapoor", "Psychiatrist"),
    ("Dr. Neha Kulkarni", "Ophthalmologist"),
    ("Dr. Rohan Joshi", "Dentist"),
    ("Dr. Meera Nambiar", "Oncologist"),
    ("Dr. Sanjay Gupta", "Endocrinologist"),
    ("Dr. Kavita Reddy", "Pulmonologist"),
    ("Dr. Amit Bansal", "Gastroenterologist"),
]

SLOT_TIMES = [
    time(9, 0),
    time(10, 0),
    time(11, 0),
    time(12, 0),
    time(14, 0),
    time(15, 0),
    time(16, 0),
    time(17, 0),
]

SERVICE_PRICES = [
    ("CONSULT", "Standard Consultation", 15000),             # $150.00
    ("FOLLOWUP", "Follow-up Consultation", 8000),             # $80.00
    ("SPECIALIST_CONSULT", "Specialist Consultation", 25000), # $250.00
    ("LAB", "Diagnostic Lab Tests", 12000),                   # $120.00
]

COVERAGE_RULES = [
    # plan_id, service_code, covered, coinsurance_percent, copay_cents, annual_limit_cents
    ("GOLD_PLAN", "CONSULT", 1, 0, 5000, 100000),             # $50 copay, 0% coinsurance
    ("GOLD_PLAN", "FOLLOWUP", 1, 0, 2500, 100000),            # $25 copay, 0% coinsurance
    ("GOLD_PLAN", "SPECIALIST_CONSULT", 1, 10, 5000, 100000), # $50 copay + 10% coinsurance
    ("GOLD_PLAN", "LAB", 1, 0, 3000, 100000),                 # $30 copay, 0% coinsurance

    ("SILVER_PLAN", "CONSULT", 1, 20, 4000, 75000),           # $40 copay + 20% coinsurance
    ("SILVER_PLAN", "FOLLOWUP", 1, 20, 2000, 75000),          # $20 copay + 20% coinsurance
    ("SILVER_PLAN", "SPECIALIST_CONSULT", 1, 30, 6000, 75000),# $60 copay + 30% coinsurance
    ("SILVER_PLAN", "LAB", 1, 20, 4000, 75000),               # $40 copay + 20% coinsurance

    ("BRONZE_PLAN", "CONSULT", 1, 30, 6000, 50000),           # $60 copay + 30% coinsurance
    ("BRONZE_PLAN", "FOLLOWUP", 1, 30, 3000, 50000),          # $30 copay + 30% coinsurance
    ("BRONZE_PLAN", "SPECIALIST_CONSULT", 1, 40, 8000, 50000),# $80 copay + 40% coinsurance
    ("BRONZE_PLAN", "LAB", 0, 0, 0, 0),                       # Explicitly not covered
]


def populate():
    print(f"Connecting to database {DB_NAME} at {DB_HOST}:{DB_PORT} as {DB_USER}...")
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )
    cursor = conn.cursor()

    try:
        # 1. Populate Doctors
        print("\n--- 1. Populating Doctors ---")
        for name, spec in DOCTORS_DATA:
            cursor.execute(
                """
                INSERT INTO doctors (name, specialization)
                SELECT %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM doctors WHERE name = %s AND specialization = %s
                );
                """,
                (name, spec, name, spec),
            )
        conn.commit()

        cursor.execute("SELECT id, name, specialization FROM doctors ORDER BY id;")
        doctors = cursor.fetchall()
        print(f"Total doctors now: {len(doctors)}")

        # 2. Populate Patients
        print("\n--- 2. Populating Patients ---")
        # Ensure our primary test patient Aarav Patel exists
        cursor.execute(
            """
            INSERT INTO patients (id, name, email, phone, created_at)
            VALUES (1, 'Aarav Patel', 'aarav@example.com', '787020112351', NOW())
            ON CONFLICT (id) DO UPDATE 
            SET name = EXCLUDED.name, email = EXCLUDED.email, phone = EXCLUDED.phone;
            """
        )

        patients_to_add = []
        base_phone = 9820010000
        for i in range(75):
            first = FIRST_NAMES[i % len(FIRST_NAMES)]
            last = LAST_NAMES[(i * 3) % len(LAST_NAMES)]
            name = f"{first} {last}"
            email = f"{first.lower()}.{last.lower()}{100 + i}@gmail.com"
            phone = str(base_phone + i)
            created_at = datetime.now() - timedelta(days=random.randint(1, 30))
            patients_to_add.append((name, email, phone, created_at))

        for name, email, phone, created_at in patients_to_add:
            cursor.execute(
                """
                INSERT INTO patients (name, email, phone, created_at)
                SELECT %s, %s, %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM patients WHERE phone = %s OR email = %s
                );
                """,
                (name, email, phone, created_at, phone, email),
            )
        conn.commit()

        cursor.execute("SELECT id, name, phone FROM patients ORDER BY id;")
        patients = cursor.fetchall()
        print(f"Total patients now: {len(patients)}")

        # 3. Populate Service Prices
        print("\n--- 3. Populating Service Prices ---")
        for code, desc, price in SERVICE_PRICES:
            cursor.execute(
                """
                INSERT INTO service_prices (service_code, description, price_cents)
                VALUES (%s, %s, %s)
                ON CONFLICT (service_code) DO UPDATE 
                SET description = EXCLUDED.description, price_cents = EXCLUDED.price_cents;
                """,
                (code, desc, price),
            )
        conn.commit()
        cursor.execute("SELECT count(*) FROM service_prices;")
        print(f"Total service prices: {cursor.fetchone()[0]}")

        # 4. Populate Coverage Rules
        print("\n--- 4. Populating Coverage Rules ---")
        for plan_id, service_code, covered, coinsurance, copay, limit in COVERAGE_RULES:
            cursor.execute(
                """
                INSERT INTO coverage_rules (plan_id, service_code, covered, coinsurance_percent, copay_cents, annual_limit_cents)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (plan_id, service_code) DO UPDATE 
                SET covered = EXCLUDED.covered,
                    coinsurance_percent = EXCLUDED.coinsurance_percent,
                    copay_cents = EXCLUDED.copay_cents,
                    annual_limit_cents = EXCLUDED.annual_limit_cents;
                """,
                (plan_id, service_code, covered, coinsurance, copay, limit),
            )
        conn.commit()
        cursor.execute("SELECT count(*) FROM coverage_rules;")
        print(f"Total coverage rules: {cursor.fetchone()[0]}")

        # 5. Populate Insurance Policies for ALL patients
        print("\n--- 5. Populating Insurance Policies for ALL Patients ---")
        PROVIDERS = [
            ("Star Health", "STAR01"),
            ("HDFC ERGO", "HDFC01"),
            ("Max Bupa", "MAX01"),
            ("Care Health", "CARE01"),
            ("ICICI Lombard", "ICICI01"),
            ("Bajaj Allianz", "BAJAJ01"),
            ("Tata AIG", "TATA01"),
        ]
        PLANS = ["GOLD_PLAN", "SILVER_PLAN", "BRONZE_PLAN"]

        cursor.execute("SELECT setval('insurance_policies_policy_id_seq', (SELECT COALESCE(MAX(policy_id), 1) FROM insurance_policies));")

        # Ensure primary test patient Aarav Patel has Gold Plan
        cursor.execute(
            """
            INSERT INTO insurance_policies (patient_id, provider_name, payer_id, policy_number, plan_id, priority, is_active, created_at)
            VALUES (1, 'Star Health', 'STAR01', 'POL-998877', 'GOLD_PLAN', 1, 1, NOW())
            ON CONFLICT (patient_id, policy_number) DO UPDATE 
            SET provider_name = EXCLUDED.provider_name,
                plan_id = EXCLUDED.plan_id,
                is_active = 1;
            """
        )

        for idx, pat in enumerate(patients):
            pat_id = pat[0]
            if pat_id == 1:
                continue
            prov_name, payer_id = PROVIDERS[idx % len(PROVIDERS)]
            plan_id = PLANS[idx % len(PLANS)]
            pol_num = f"POL-{100000 + pat_id}"
            cursor.execute(
                """
                INSERT INTO insurance_policies (patient_id, provider_name, payer_id, policy_number, plan_id, priority, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, 1, 1, NOW())
                ON CONFLICT (patient_id, policy_number) DO UPDATE 
                SET provider_name = EXCLUDED.provider_name,
                    plan_id = EXCLUDED.plan_id,
                    is_active = 1;
                """,
                (pat_id, prov_name, payer_id, pol_num, plan_id),
            )
        conn.commit()
        cursor.execute("SELECT count(*) FROM insurance_policies;")
        print(f"Total insurance policies: {cursor.fetchone()[0]}")

        # 6. Populate Doctor Availability Slots for upcoming 21 days
        print("\n--- 6. Populating Doctor Availability (Next 21 days from today) ---")
        today = date.today()
        slots_created = 0

        for doc in doctors:
            doc_id = doc[0]
            # Days from today (day 0) through 21 days ahead
            for day_offset in range(0, 22):
                slot_date = today + timedelta(days=day_offset)
                # Skip Sundays
                if slot_date.weekday() == 6:
                    continue
                # Assign 5-7 slots per doctor per day
                daily_slots = random.sample(SLOT_TIMES, k=random.randint(5, 7))
                for slot_time in daily_slots:
                    cursor.execute(
                        """
                        INSERT INTO doctor_availability (doctor_id, available_date, slot_time, is_booked)
                        VALUES (%s, %s, %s, FALSE)
                        ON CONFLICT (doctor_id, available_date, slot_time) DO NOTHING;
                        """,
                        (doc_id, slot_date, slot_time),
                    )
                    if cursor.rowcount > 0:
                        slots_created += 1
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM doctor_availability WHERE available_date >= CURRENT_DATE;")
        future_slots = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM doctor_availability WHERE available_date >= CURRENT_DATE AND is_booked = FALSE;")
        future_open_slots = cursor.fetchone()[0]
        print(f"Created {slots_created} new availability slots.")
        print(f"Future slots total: {future_slots}, Open: {future_open_slots}")

        # 7. Ensure Test Appointments exist and are valid
        print("\n--- 7. Synchronizing Appointments & Test Records ---")
        # Make sure slot for test appointment 101 exists and is marked booked
        test_appt_date = today + timedelta(days=2) # 2 days from today
        test_appt_time = time(10, 0)

        cursor.execute(
            """
            INSERT INTO doctor_availability (doctor_id, available_date, slot_time, is_booked)
            VALUES (1, %s, %s, TRUE)
            ON CONFLICT (doctor_id, available_date, slot_time) 
            DO UPDATE SET is_booked = TRUE;
            """,
            (test_appt_date, test_appt_time),
        )

        cursor.execute(
            """
            INSERT INTO appointments (id, patient_id, doctor_id, appointment_date, appointment_time, status)
            VALUES (101, 1, 1, %s, %s, 'booked')
            ON CONFLICT (id) DO UPDATE 
            SET patient_id = 1,
                doctor_id = 1,
                appointment_date = EXCLUDED.appointment_date,
                appointment_time = EXCLUDED.appointment_time,
                status = 'booked';
            """,
            (test_appt_date, test_appt_time),
        )

        # Make sure insurance check for appointment 101 exists
        cursor.execute(
            """
            INSERT INTO insurance_checks (check_id, appointment_id, policy_id, status, visit_cost_cents, insurer_amount_cents, patient_amount_cents, needs_manual_review, checked_at)
            VALUES (4, 101, 1, 'covered', 15000, 10000, 5000, 0, NOW())
            ON CONFLICT (check_id) DO UPDATE 
            SET appointment_id = 101,
                policy_id = 1,
                status = 'covered',
                visit_cost_cents = 15000,
                insurer_amount_cents = 10000,
                patient_amount_cents = 5000;
            """
        )

        # Populate some realistic appointments for other upcoming slots
        cursor.execute(
            """
            SELECT id, doctor_id, available_date, slot_time
            FROM doctor_availability
            WHERE is_booked = FALSE AND available_date > CURRENT_DATE
            ORDER BY available_date, slot_time
            LIMIT 20;
            """
        )
        sample_open_slots = cursor.fetchall()
        for idx, (slot_id, doc_id, appt_date, appt_time) in enumerate(sample_open_slots[:10]):
            pat_id = patients[(idx + 2) % len(patients)][0]
            cursor.execute(
                """
                INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, status)
                VALUES (%s, %s, %s, %s, 'booked')
                ON CONFLICT (doctor_id, appointment_date, appointment_time) DO NOTHING;
                """,
                (pat_id, doc_id, appt_date, appt_time),
            )
            if cursor.rowcount > 0:
                cursor.execute(
                    "UPDATE doctor_availability SET is_booked = TRUE WHERE id = %s;",
                    (slot_id,),
                )
        conn.commit()

        # Final Summary
        print("\n================== Database Population Summary ==================")
        for table in [
            "patients", "doctors", "service_prices", "coverage_rules",
            "insurance_policies", "doctor_availability", "appointments", "insurance_checks", "invoices"
        ]:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"  {table.ljust(22)}: {count} records")
        print("=================================================================\n")

    except Exception as e:
        conn.rollback()
        print(f"Error during population: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    populate()
