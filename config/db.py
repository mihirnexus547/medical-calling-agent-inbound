"""PostgreSQL connection and shared cursor."""

import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    dbname="patient_db",
    user="postgres",
    password="postgres",
    host="localhost",
    port="5432",
)

cursor = conn.cursor()
