"""Insurance Agent definition and handoff tool."""

import time
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver

from config import logger
from tools.insurance_tools import check_insurance_eligibility
from agents.callbacks import AgentLoggingCallback

checkpointer = InMemorySaver()


@tool
def handoff_to_insurance(patient_id: int, request: str) -> str:
    """Call this tool to transfer the user to the Insurance Agent to check insurance eligibility or copays."""
    start_time = time.perf_counter()
    logger.info("Handoff to Insurance Agent started: patient_id=%s, request=%s", patient_id, request)
    try:
        insurance_config = {
            "configurable": {"thread_id": f"insurance_patient_{patient_id}"},
            "callbacks": [AgentLoggingCallback()],
        }
        response = insurance_agent.invoke(
            {"messages": [{"role": "user", "content": f"Patient ID: {patient_id}, Request: {request}"}]},
            config=insurance_config,
        )
        duration = time.perf_counter() - start_time
        logger.info("Handoff to Insurance Agent completed: patient_id=%s duration=%.3fs", patient_id, duration)
        return response["messages"][-1].content
    except Exception as e:
        logger.exception("Handoff to Insurance Agent failed: %s", e)
        return f"Failed to process insurance request: {str(e)}"


# Import handoff_to_billing dynamically to avoid circular references
def _get_handoff_to_billing():
    from agents.billing import handoff_to_billing
    return handoff_to_billing


import os
from dotenv import load_dotenv

load_dotenv()

insurance_agent = create_agent(
    model=ChatGroq(model_name=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), temperature=0),
    system_prompt=(
        "You are the Insurance Agent, a specialized AI assistant.\n"
        "Your ONLY job is to verify patient insurance coverage and calculate costs.\n"
        "Rules:\n"
        "1. Always use your check_insurance_eligibility tool to calculate costs. If the user does not specify a service_code, default to 'CONSULT'.\n"
        "2. Never call more than one tool in a single turn.\n"
        "3. If the user also asks for a bill or invoice, FIRST complete check_insurance_eligibility, wait for the tool output, and ONLY call handoff_to_billing in your next turn after the check is finished.\n"
        "4. When calling handoff_to_billing, include the appointment_id, service_code, and the check_id in your request string, and relay the returned response directly to the user.\n"
        "5. Be concise and report the final patient amount, insurer amount, and the check_id."
    ),
    tools=[check_insurance_eligibility, _get_handoff_to_billing()],
    checkpointer=checkpointer,
)
