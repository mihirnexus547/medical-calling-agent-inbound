"""
Script to populate patient_db with at least 50 realistic records across
patients, doctors, doctor availability slots, and appointments.
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
        print("\n--- Populating Doctors ---")
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

        # 2. Populate at least 60 Patients
        print("\n--- Populating Patients ---")
        patients_to_add = []
        base_phone = 9820010000
        for i in range(65):
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
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (phone) DO NOTHING;
                """,
                (name, email, phone, created_at),
            )
        conn.commit()

        cursor.execute("SELECT id, name, phone FROM patients ORDER BY id;")
        patients = cursor.fetchall()
        print(f"Total patients now: {len(patients)}")

        # 3. Populate Doctor Availability Slots across upcoming dates
        print("\n--- Populating Doctor Availability ---")
        base_date = date.today() + timedelta(days=1)
        availability_count_before = 0
        cursor.execute("SELECT COUNT(*) FROM doctor_availability;")
        availability_count_before = cursor.fetchone()[0]

        slots_created = 0
        for doc in doctors:
            doc_id = doc[0]
            # Create availability for next 7 days for each doctor
            for day_offset in range(1, 8):
                slot_date = base_date + timedelta(days=day_offset)
                # Skip Sundays
                if slot_date.weekday() == 6:
                    continue
                # Assign 4-6 slots per doctor per day
                daily_slots = random.sample(SLOT_TIMES, k=random.randint(4, 6))
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

        cursor.execute("SELECT COUNT(*) FROM doctor_availability;")
        total_slots = cursor.fetchone()[0]
        print(f"Created {slots_created} new availability slots. Total slots now: {total_slots}")

        # 4. Populate at least 50 Appointments
        print("\n--- Populating Appointments ---")
        cursor.execute("SELECT COUNT(*) FROM appointments;")
        current_appt_count = cursor.fetchone()[0]
        target_appts = max(50, current_appt_count + 48)

        # Fetch available slots that are currently not booked
        cursor.execute(
            """
            SELECT id, doctor_id, available_date, slot_time
            FROM doctor_availability
            WHERE is_booked = FALSE
            ORDER BY available_date, slot_time;
            """
        )
        available_slots = cursor.fetchall()
        random.shuffle(available_slots)

        appts_created = 0
        patient_idx = 0

        for slot_id, doc_id, appt_date, appt_time in available_slots:
            if current_appt_count + appts_created >= target_appts:
                break

            patient_id = patients[patient_idx % len(patients)][0]
            patient_idx += 1

            # 85% booked, 15% cancelled
            status = "booked" if random.random() < 0.85 else "cancelled"

            try:
                cursor.execute(
                    """
                    INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, status)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (doctor_id, appointment_date, appointment_time) DO NOTHING
                    RETURNING id;
                    """,
                    (patient_id, doc_id, appt_date, appt_time, status),
                )
                inserted = cursor.fetchone()
                if inserted:
                    if status == "booked":
                        cursor.execute(
                            """
                            UPDATE doctor_availability
                            SET is_booked = TRUE
                            WHERE id = %s;
                            """,
                            (slot_id,),
                        )
                    appts_created += 1
                    conn.commit()
            except Exception as e:
                conn.rollback()
                continue

        cursor.execute("SELECT COUNT(*) FROM appointments;")
        total_appts = cursor.fetchone()[0]
        print(f"Created {appts_created} new appointments. Total appointments now: {total_appts}")

        # Final Summary
        print("\n================== Database Population Summary ==================")
        for table in ["patients", "doctors", "doctor_availability", "appointments"]:
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
