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

def get_chat_llm(temperature: float = 0.1):
    from langchain_groq import ChatGroq

    primary_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    fallback_model = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")

    primary = ChatGroq(
        model_name=primary_model,
        temperature=temperature,
        max_retries=0,
    )
    fallback = ChatGroq(
        model_name=fallback_model,
        temperature=temperature,
    )
    return primary.with_fallbacks([fallback])


from .callbacks import AgentLoggingCallback
from .receptionist import receptionist_agent, thread_config, handoff_to_appointment_agent
from .appointment import appointment_agent
from .insurance import insurance_agent, handoff_to_insurance
from .billing import billing_agent, handoff_to_billing

__all__ = [
    "get_chat_llm",
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
