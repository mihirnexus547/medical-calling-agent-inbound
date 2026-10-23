import os
from dotenv import load_dotenv

load_dotenv()

# Ensure LangChain / LangSmith tracing is active for all agents
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "mca_multiagent_inbound")
os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
_ls_key = os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
if _ls_key:
    os.environ["LANGCHAIN_API_KEY"] = _ls_key
    os.environ["LANGSMITH_API_KEY"] = _ls_key

from .callbacks import AgentLoggingCallback
from .receptionist import receptionist_agent, thread_config, handoff_to_appointment_agent
from .appointment import appointment_agent
from .insurance import insurance_agent, handoff_to_insurance
from .billing import billing_agent, handoff_to_billing

__all__ = [
    "AgentLoggingCallback",
    "receptionist_agent",
    "thread_config",
    "appointment_agent",
    "handoff_to_appointment_agent",
    "insurance_agent",
    "handoff_to_insurance",
    "billing_agent",
    "handoff_to_billing",
]
