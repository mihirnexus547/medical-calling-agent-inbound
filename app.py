"""
Medical Calling Agent - Unified Receptionist, AI Assistant & Admin Portal
Built with Streamlit.
Includes:
- Tab 1: AI Patient Chat UI (Interactive Multi-Agent Assistant)
- Tab 2: Receptionist Calendar & Appointment Board (Visual slot/booking manager)
- Tab 3: Admin Database Center (Full CRUD for all tables)
"""

import time
from datetime import date, datetime, timedelta
import pandas as pd
import psycopg2
import streamlit as st

# Configure Page
st.set_page_config(
    page_title="MediFlow AI | Inbound Clinic Receptionist",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Premium Medical / Glassmorphic Aesthetic
st.markdown(
    """
    <style>
    /* Global Styles */
    .main {
        background-color: #0b1120;
    }
    .stApp {
        background: radial-gradient(circle at top right, #1e293b, #0f172a, #0b1120);
        color: #f1f5f9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    /* Metric Cards */
    div[data-testid="stMetricValue"] {
        font-size: 26px;
        font-weight: 700;
        color: #38bdf8;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 13px;
        font-weight: 500;
        color: #94a3b8;
    }
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        border-bottom: 1px solid #334155;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        border-radius: 8px 8px 0px 0px;
        padding: 0 20px;
        color: #94a3b8;
        font-weight: 600;
        background-color: transparent;
    }
    .stTabs [aria-selected="true"] {
        color: #38bdf8 !important;
        border-bottom: 2px solid #38bdf8 !important;
        background-color: rgba(56, 189, 248, 0.08) !important;
    }
    /* Card Containers */
    .medical-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 16px;
        transition: all 0.2s ease;
    }
    .medical-card:hover {
        border-color: #38bdf8;
        box-shadow: 0 4px 20px rgba(56, 189, 248, 0.12);
    }
    /* Status Badges */
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    .badge-booked { background-color: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #38bdf8; }
    .badge-paid { background-color: rgba(52, 211, 153, 0.2); color: #34d399; border: 1px solid #34d399; }
    .badge-cancelled { background-color: rgba(248, 113, 113, 0.2); color: #f87171; border: 1px solid #f87171; }
    .badge-pending { background-color: rgba(251, 191, 36, 0.2); color: #fbbf24; border: 1px solid #fbbf24; }
    </style>
    """,
    unsafe_allow_html=True,
)


# Database Helper Functions
def get_db_connection():
    return psycopg2.connect(
        dbname="patient_db",
        user="postgres",
        password="postgres",
        host="localhost",
        port="5432",
    )


def run_query(query, params=None, is_select=True):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if is_select:
                cols = [desc[0] for desc in cur.description] if cur.description else []
                data = cur.fetchall()
                return pd.DataFrame(data, columns=cols)
            else:
                conn.commit()
                return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# Lazy load agent
@st.cache_resource
def load_agent():
    from agents.receptionist import receptionist_agent, AgentLoggingCallback
    return receptionist_agent, AgentLoggingCallback


# Initialize Session State
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {"role": "assistant", "content": "Hello! I am your AI Medical Receptionist. How can I assist you today? Please feel free to share your phone number to get started."}
    ]

if "session_thread_id" not in st.session_state:
    st.session_state.session_thread_id = f"st_session_{int(time.time())}"


# Header
col_logo, col_title, col_status = st.columns([1, 6, 2])
with col_logo:
    st.markdown("<h1 style='font-size: 42px; margin: 0;'>🩺</h1>", unsafe_allow_html=True)
with col_title:
    st.markdown("<h2 style='margin: 0; color: #f8fafc;'>MediFlow AI Receptionist & Clinic Portal</h2>", unsafe_allow_html=True)
    st.markdown("<p style='margin: 0; color: #94a3b8; font-size: 14px;'>Multi-Agent Autonomous Inbound Healthcare Assistant</p>", unsafe_allow_html=True)
with col_status:
    st.markdown(
        """
        <div style='text-align: right; padding-top: 8px;'>
            <span class='badge badge-paid'>● Database Online</span>
            <span class='badge badge-booked'>● AI Multi-Agent Ready</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<hr style='border: none; border-top: 1px solid #334155; margin: 15px 0 25px 0;'>", unsafe_allow_html=True)


# Sidebar - Quick Stats & Helpers
with st.sidebar:
    st.markdown("### 🏥 Clinic Dashboard")
    try:
        total_pats = run_query("SELECT count(*) FROM patients;").iloc[0, 0]
        total_appts = run_query("SELECT count(*) FROM appointments WHERE status = 'booked';").iloc[0, 0]
        open_slots = run_query("SELECT count(*) FROM doctor_availability WHERE available_date >= CURRENT_DATE AND is_booked = FALSE;").iloc[0, 0]
        paid_invs = run_query("SELECT count(*) FROM invoices WHERE status = 'paid';").iloc[0, 0]

        st.metric("Total Patients", f"{total_pats:,}")
        st.metric("Active Bookings", f"{total_appts:,}")
        st.metric("Open Slots (Next 21 Days)", f"{open_slots:,}")
        st.metric("Paid Invoices", f"{paid_invs:,}")
    except Exception as e:
        st.error(f"DB Error: {e}")

    st.markdown("---")
    st.markdown("#### ⚡ Quick Test Profiles")
    st.markdown(
        """
        - **Aarav Patel (Gold Plan)**  
          `787020112351` (Appt #101)
        - **Mihir Bhavsar (Gold Plan)**  
          `919723118363`
        - **Harsh Panchal (Bronze Plan)**  
          `7984134319`
        - **Gautam Mahto (Silver Plan)**  
          `919878451262`
        """
    )

    if st.button("🔄 Reset AI Chat Session", use_container_width=True):
        st.session_state.session_thread_id = f"st_session_{int(time.time())}"
        st.session_state.chat_messages = [
            {"role": "assistant", "content": "Hello! I am your AI Medical Receptionist. How can I assist you today? Please share your phone number to get started."}
        ]
        st.rerun()


# Main Application Tabs
tab_chat, tab_calendar, tab_admin = st.tabs([
    "💬 AI Patient Assistant (Chat)",
    "📅 Receptionist Calendar & Bookings",
    "🛠️ Admin Database Center",
])


# ==============================================================================
# TAB 1: AI PATIENT CHAT ASSISTANT
# ==============================================================================
with tab_chat:
    col_c1, col_c2 = st.columns([7, 3])

    with col_c2:
        st.markdown("#### 🚀 Quick Action Prompts")
        st.caption("Click any prompt to instantly send to the agent:")

        quick_prompts = [
            ("📞 Identify as Aarav Patel", "Hi, my phone number is 787020112351"),
            ("📅 Check My Appointments", "Can you check what upcoming appointments I currently have?"),
            ("🩺 Available Dermatologists", "Which dermatologists do you have available?"),
            ("🕒 Dr. Sharma Slots on Monday", "What open slots does Dr. Sharma have next Monday?"),
            ("💳 Check Insurance for Appt 101", "Can you check my insurance coverage for appointment 101?"),
            ("💵 Generate Stripe Payment Link", "Please generate an invoice and payment link for appointment 101"),
            ("🔍 Check Payment Status", "Is my payment done for appointment 101?"),
        ]

        for label, prompt_text in quick_prompts:
            if st.button(label, key=f"qp_{label}", use_container_width=True):
                st.session_state.pending_user_input = prompt_text
                st.rerun()

    with col_c1:
        st.markdown("#### 🗨️ Live Conversation")

        # Display Chat History
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                with st.chat_message("user", avatar="👤"):
                    st.markdown(msg["content"])
            else:
                with st.chat_message("assistant", avatar="🩺"):
                    st.markdown(msg["content"])

        # Handle Quick Prompt Input or Chat Input
        user_prompt = st.chat_input("Type your message here (e.g., 'Check slots for Dr. Sharma next Friday')...")
        if getattr(st.session_state, "pending_user_input", None):
            user_prompt = st.session_state.pending_user_input
            del st.session_state["pending_user_input"]

        if user_prompt:
            st.session_state.chat_messages.append({"role": "user", "content": user_prompt})
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_prompt)

            with st.chat_message("assistant", avatar="🩺"):
                with st.spinner("AI Agent thinking & coordinating with specialists..."):
                    try:
                        agent, logging_cb = load_agent()
                        start_t = time.perf_counter()
                        config = {
                            "configurable": {"thread_id": st.session_state.session_thread_id},
                            "callbacks": [logging_cb()],
                        }
                        res = agent.invoke(
                            {"messages": [{"role": "user", "content": user_prompt}]},
                            config=config,
                        )
                        elapsed = time.perf_counter() - start_t
                        bot_reply = res["messages"][-1].content

                        st.markdown(bot_reply)
                        st.caption(f"⏱️ Response latency: {elapsed:.2f}s | Thread: {st.session_state.session_thread_id}")

                        st.session_state.chat_messages.append({"role": "assistant", "content": bot_reply})
                    except Exception as e:
                        err_msg = f"Sorry, an error occurred: {str(e)}"
                        st.error(err_msg)
                        st.session_state.chat_messages.append({"role": "assistant", "content": err_msg})


# ==============================================================================
# TAB 2: RECEPTIONIST CALENDAR & APPOINTMENT BOARD
# ==============================================================================
with tab_calendar:
    st.markdown("### 📅 Clinic Appointments & Schedule Board")
    st.markdown("View all scheduled bookings, manage cancellations, reschedule appointments, and inspect doctor availability slots.")

    cal_col1, cal_col2, cal_col3 = st.columns([3, 3, 2])

    with cal_col1:
        # Date Filter
        selected_date = st.date_input("Filter by Date:", value=date.today())
    with cal_col2:
        # Doctor Filter
        docs_df = run_query("SELECT id, name, specialization FROM doctors ORDER BY name;")
        doc_options = ["All Doctors"] + [f"{r['name']} ({r['specialization']})" for _, r in docs_df.iterrows()]
        selected_doc = st.selectbox("Filter by Doctor:", doc_options)
    with cal_col3:
        status_filter = st.selectbox("Appointment Status:", ["All", "booked", "cancelled", "completed"])

    # Query Appointments
    query_appt = """
        SELECT 
            a.id AS appt_id,
            p.name AS patient_name,
            p.phone AS patient_phone,
            d.name AS doctor_name,
            d.specialization,
            a.appointment_date,
            a.appointment_time,
            a.status,
            COALESCE(i.status, 'no_invoice') AS invoice_status,
            COALESCE(i.patient_amount_cents, 0) AS patient_amount_cents
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        LEFT JOIN invoices i ON a.id = i.appointment_id
        WHERE 1=1
    """
    params = []
    if selected_date:
        query_appt += " AND a.appointment_date = %s"
        params.append(selected_date)
    if selected_doc != "All Doctors":
        doc_name_only = selected_doc.split(" (")[0]
        query_appt += " AND d.name = %s"
        params.append(doc_name_only)
    if status_filter != "All":
        query_appt += " AND a.status = %s"
        params.append(status_filter)

    query_appt += " ORDER BY a.appointment_date, a.appointment_time;"

    appts_df = run_query(query_appt, params)

    st.markdown(f"#### 📋 Bookings for {selected_date.strftime('%A, %b %d, %Y')} ({len(appts_df)} found)")

    if appts_df.empty:
        st.info(f"No appointments found matching your filters for {selected_date}. Check another date or open slots below.")
    else:
        for _, row in appts_df.iterrows():
            with st.container():
                st.markdown(
                    f"""
                    <div class="medical-card">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <span style="font-size: 18px; font-weight: 700; color: #38bdf8;">#{row['appt_id']} - {row['patient_name']}</span>
                                <span style="color: #94a3b8; font-size: 14px; margin-left: 10px;">📞 {row['patient_phone']}</span>
                            </div>
                            <div>
                                <span class="badge badge-{row['status']}">{row['status'].upper()}</span>
                                <span class="badge badge-{'paid' if row['invoice_status'] == 'paid' else 'pending'}">INV: {row['invoice_status'].upper()}</span>
                            </div>
                        </div>
                        <div style="margin-top: 10px; color: #cbd5e1; font-size: 15px;">
                            👨‍⚕️ <strong>{row['doctor_name']}</strong> ({row['specialization']}) &nbsp;|&nbsp; 
                            🕒 <strong>{row['appointment_time']}</strong> &nbsp;|&nbsp;
                            💵 Balance: <strong>${row['patient_amount_cents'] / 100:.2f}</strong>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Quick Actions for this appointment
                col_act1, col_act2, col_act3 = st.columns([2, 3, 5])
                with col_act1:
                    if row["status"] == "booked":
                        if st.button("❌ Cancel Booking", key=f"cancel_{row['appt_id']}"):
                            run_query("UPDATE appointments SET status = 'cancelled' WHERE id = %s;", (row["appt_id"],), is_select=False)
                            run_query(
                                """
                                UPDATE doctor_availability da
                                SET is_booked = FALSE
                                FROM appointments a
                                WHERE a.id = %s AND da.doctor_id = a.doctor_id 
                                  AND da.available_date = a.appointment_date 
                                  AND da.slot_time = a.appointment_time;
                                """,
                                (row["appt_id"],),
                                is_select=False,
                            )
                            st.success(f"Appointment #{row['appt_id']} cancelled and slot freed.")
                            st.rerun()

    st.markdown("---")
    st.markdown("#### 🕒 Open Availability Slots Explorer")
    slot_col1, slot_col2 = st.columns([1, 1])
    with slot_col1:
        slot_date_check = st.date_input("Check slots on date:", value=selected_date, key="slot_date_check")
    with slot_col2:
        slot_doc_check = st.selectbox("For Doctor:", [r["name"] for _, r in docs_df.iterrows()], key="slot_doc_check")

    open_slots_df = run_query(
        """
        SELECT da.id AS slot_id, d.name AS doctor, d.specialization, da.available_date, da.slot_time
        FROM doctor_availability da
        JOIN doctors d ON da.doctor_id = d.id
        WHERE da.available_date = %s AND d.name = %s AND da.is_booked = FALSE
        ORDER BY da.slot_time;
        """,
        (slot_date_check, slot_doc_check),
    )

    if open_slots_df.empty:
        st.warning(f"No open slots for {slot_doc_check} on {slot_date_check}.")
    else:
        st.success(f"{len(open_slots_df)} open slots available on {slot_date_check}:")
        st.dataframe(
            open_slots_df[["doctor", "specialization", "available_date", "slot_time"]],
            use_container_width=True,
            hide_index=True,
        )


# ==============================================================================
# TAB 3: ADMIN DATABASE CENTER (FULL CRUD)
# ==============================================================================
with tab_admin:
    st.markdown("### 🛠️ Administrative Database Management")
    st.markdown("Inspect, insert, update, and manage records across all clinic tables.")

    tables = [
        "patients",
        "appointments",
        "doctors",
        "doctor_availability",
        "invoices",
        "insurance_policies",
        "coverage_rules",
        "service_prices",
        "payment_events",
    ]

    selected_table = st.selectbox("📁 Select Database Table:", tables)

    # 1. View Table Records
    st.markdown(f"#### 📊 Records in `{selected_table}`")

    search_term = st.text_input(f"🔍 Search `{selected_table}` (text search):", "")
    limit_rows = st.slider("Limit rows to display:", 10, 200, 50)

    try:
        raw_df = run_query(f"SELECT * FROM {selected_table} LIMIT {limit_rows};")
        if search_term:
            filtered_df = raw_df[
                raw_df.astype(str).apply(lambda row: row.str.contains(search_term, case=False).any(), axis=1)
            ]
        else:
            filtered_df = raw_df

        st.dataframe(filtered_df, use_container_width=True)
        st.caption(f"Showing {len(filtered_df)} of total rows in `{selected_table}`.")
    except Exception as e:
        st.error(f"Failed to load table: {e}")

    # 2. Insert Record Section
    st.markdown("---")
    st.markdown(f"#### ➕ Insert New Record into `{selected_table}`")

    with st.expander(f"Open Insert Form for `{selected_table}`"):
        if selected_table == "patients":
            with st.form("insert_patient_form"):
                p_name = st.text_input("Full Name:")
                p_email = st.text_input("Email:")
                p_phone = st.text_input("Phone Number:")
                sub_pat = st.form_submit_button("Create Patient")
                if sub_pat:
                    if p_name and p_phone:
                        run_query(
                            "INSERT INTO patients (name, email, phone, created_at) VALUES (%s, %s, %s, NOW());",
                            (p_name, p_email, p_phone),
                            is_select=False,
                        )
                        st.success(f"Patient '{p_name}' successfully inserted.")
                        st.rerun()
                    else:
                        st.warning("Name and Phone are required.")

        elif selected_table == "doctors":
            with st.form("insert_doctor_form"):
                d_name = st.text_input("Doctor Name (e.g. Dr. John Doe):")
                d_spec = st.text_input("Specialization (e.g. Cardiologist):")
                sub_doc = st.form_submit_button("Create Doctor")
                if sub_doc:
                    if d_name and d_spec:
                        run_query(
                            "INSERT INTO doctors (name, specialization) VALUES (%s, %s);",
                            (d_name, d_spec),
                            is_select=False,
                        )
                        st.success(f"Doctor '{d_name}' successfully added.")
                        st.rerun()

        elif selected_table == "service_prices":
            with st.form("insert_service_form"):
                s_code = st.text_input("Service Code (e.g. XRAY):").upper()
                s_desc = st.text_input("Description:")
                s_cents = st.number_input("Price in Cents (e.g. 10000 = $100):", min_value=100, step=500, value=10000)
                sub_srv = st.form_submit_button("Add Service Price")
                if sub_srv:
                    run_query(
                        "INSERT INTO service_prices (service_code, description, price_cents) VALUES (%s, %s, %s);",
                        (s_code, s_desc, int(s_cents)),
                        is_select=False,
                    )
                    st.success(f"Service price for '{s_code}' added.")
                    st.rerun()

        elif selected_table == "coverage_rules":
            with st.form("insert_coverage_form"):
                cr_plan = st.selectbox("Plan ID:", ["GOLD_PLAN", "SILVER_PLAN", "BRONZE_PLAN"])
                cr_code = st.text_input("Service Code:", value="CONSULT").upper()
                cr_cov = st.selectbox("Covered:", [1, 0])
                cr_coin = st.number_input("Coinsurance %:", min_value=0, max_value=100, value=20)
                cr_copay = st.number_input("Copay Cents:", min_value=0, step=500, value=4000)
                cr_limit = st.number_input("Annual Limit Cents:", min_value=0, step=5000, value=75000)
                sub_cov = st.form_submit_button("Add Coverage Rule")
                if sub_cov:
                    run_query(
                        """
                        INSERT INTO coverage_rules (plan_id, service_code, covered, coinsurance_percent, copay_cents, annual_limit_cents)
                        VALUES (%s, %s, %s, %s, %s, %s);
                        """,
                        (cr_plan, cr_code, cr_cov, cr_coin, cr_copay, cr_limit),
                        is_select=False,
                    )
                    st.success(f"Coverage rule added for {cr_plan} - {cr_code}.")
                    st.rerun()

        elif selected_table == "appointments":
            with st.form("insert_appt_form"):
                pats_list = run_query("SELECT id, name, phone FROM patients ORDER BY name;")
                p_select = st.selectbox("Select Patient:", [f"{r['id']} - {r['name']} ({r['phone']})" for _, r in pats_list.iterrows()])
                d_select = st.selectbox("Select Doctor:", [f"{r['id']} - {r['name']}" for _, r in docs_df.iterrows()])
                a_date = st.date_input("Appointment Date:", value=date.today() + timedelta(days=1))
                a_time = st.time_input("Appointment Time:", value=datetime.strptime("10:00", "%H:%M").time())
                a_status = st.selectbox("Status:", ["booked", "scheduled", "completed", "cancelled"])
                sub_appt = st.form_submit_button("Book Appointment")
                if sub_appt:
                    pat_id = int(p_select.split(" - ")[0])
                    doc_id = int(d_select.split(" - ")[0])
                    run_query(
                        """
                        INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, status)
                        VALUES (%s, %s, %s, %s, %s);
                        """,
                        (pat_id, doc_id, a_date, a_time, a_status),
                        is_select=False,
                    )
                    st.success("Appointment created successfully.")
                    st.rerun()

        else:
            st.info(f"Custom form for `{selected_table}` can be executed using the SQL query box below.")

    # 3. Delete Record Section
    st.markdown("---")
    st.markdown(f"#### 🗑️ Delete Record from `{selected_table}`")

    with st.expander(f"Open Delete Manager for `{selected_table}`"):
        primary_key_map = {
            "patients": "id",
            "appointments": "id",
            "doctors": "id",
            "doctor_availability": "id",
            "invoices": "invoice_id",
            "insurance_policies": "policy_id",
            "service_prices": "service_code",
            "payment_events": "event_id",
        }
        pk_col = primary_key_map.get(selected_table, "id")

        del_id = st.text_input(f"Enter {pk_col} to delete:")
        confirm_del = st.checkbox("I confirm I want to permanently delete this record.")

        if st.button(f"Delete from {selected_table}", type="primary"):
            if del_id and confirm_del:
                try:
                    run_query(f"DELETE FROM {selected_table} WHERE {pk_col} = %s;", (del_id,), is_select=False)
                    st.success(f"Record with {pk_col}='{del_id}' deleted from `{selected_table}`.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")
            else:
                st.warning("Please specify an ID and check the confirmation box.")

    # 4. Database Sync Utilities
    st.markdown("---")
    st.markdown("#### 🔄 Database Maintenance Utilities")
    col_ut1, col_ut2 = st.columns(2)
    with col_ut1:
        if st.button("⚡ Run Full DB Population Script", use_container_width=True):
            with st.spinner("Populating doctors, slots, policies, and test cases..."):
                from populate_db import populate
                try:
                    populate()
                    st.success("Database populated and synchronized successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Population script error: {e}")
    with col_ut2:
        if st.button("🧹 Free Stale Doctor Slots", use_container_width=True):
            run_query("DELETE FROM doctor_availability WHERE available_date < CURRENT_DATE;", is_select=False)
            st.success("Historical slots cleared.")
            st.rerun()
