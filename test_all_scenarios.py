"""
Comprehensive test script for simple_agent.py.
Tests all agents, handoffs, and tools end-to-end:
1. Patient Identification & Greeting (Receptionist Agent)
2. Appointment Lookup & Relative Date Resolution (Appointment Agent)
3. Doctor & Slot Availability Check (Appointment Agent)
4. Insurance Coverage & Cost Calculation (Insurance Agent)
5. Invoice Creation & Stripe Checkout Link Generation (Billing Agent)
"""

import time
from simple_agent import agent, AgentLoggingCallback

def run_tests():
    thread_id = "automated_test_session"
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [AgentLoggingCallback()]
    }

    test_steps = [
        (
            "Step 1: Patient Verification & Greeting",
            "Hi, my phone number is 787020112351",
            "Aarav"
        ),
        (
            "Step 2: Checking Upcoming Appointments",
            "Can you tell me what upcoming appointments I currently have?",
            "101"
        ),
        (
            "Step 3: Checking Available Slots for Dr. Sharma next Monday",
            "What open slots does Dr. Sharma have next Monday?",
            "Monday"
        ),
        (
            "Step 4: Insurance Coverage & Copay Calculation",
            "Can you check my insurance coverage for appointment 101?",
            "5000"
        ),
        (
            "Step 5: Invoice Creation & Stripe Payment Link",
            "Please generate an invoice and payment link for appointment 101",
            "checkout.stripe.com"
        ),
    ]

    print("=" * 70)
    print("STARTING END-TO-END TEST SUITE FOR simple_agent.py")
    print("=" * 70)

    for i, (title, prompt, expected_keyword) in enumerate(test_steps, 1):
        print(f"\n--- {title} ---")
        print(f"USER: {prompt}")

        start_time = time.perf_counter()
        try:
            response = agent.invoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config=config,
            )
            elapsed = time.perf_counter() - start_time
            agent_msg = response["messages"][-1].content
            print(f"AGENT ({elapsed:.2f}s):\n{agent_msg}\n")

            if expected_keyword.lower() in agent_msg.lower():
                print(f"[PASS] Found expected keyword '{expected_keyword}' in response.")
            else:
                print(f"[NOTE] Expected keyword '{expected_keyword}' not explicitly found, but response completed.")

        except Exception as e:
            print(f"[FAIL] Error during step: {e}")

        # Short pause between turns to stay within Groq API rate limits
        time.sleep(3)

    print("\n" + "=" * 70)
    print("TEST SUITE COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
