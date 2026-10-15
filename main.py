import os

from agents.receptionist import receptionist_agent, thread_config
from agents.callbacks import AgentLoggingCallback
from config import logger

import time

os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_PROJECT"] = "mca_multiagent_inbound"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"


def main():
    logger.info("Receptionist agent initialized")
    print("Receptionist & Appointment system initialized. Type 'exit' to quit.\n")

    while True:
        user_input = input("User: ")

        if user_input.strip().lower() in ["exit", "quit"]:
            logger.info("Receptionist session ended")
            break

        start_time = time.perf_counter()
        logger.info("Agent request started")

        try:
            response = receptionist_agent.invoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config={**thread_config, "callbacks": [AgentLoggingCallback()]},
            )
            elapsed = time.perf_counter() - start_time
            logger.info("Agent request completed: latency=%.3fs", elapsed)
            print(f"Agent: {response['messages'][-1].content}")
            print(f"Latency: {elapsed:.2f} seconds\n")

        except Exception:
            elapsed = time.perf_counter() - start_time
            logger.exception("Agent request failed after %.3fs", elapsed)
            print("Sorry, something went wrong. Please try again.\n")


if __name__ == "__main__":
    main()
