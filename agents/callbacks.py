"""LangChain callback handler for structured agent logging."""

from langchain_core.callbacks import BaseCallbackHandler

from config import logger


class AgentLoggingCallback(BaseCallbackHandler):
    def on_tool_start(self, serialized, input_str, **kwargs):
        tool_name = serialized.get("name", "unknown")
        logger.info("Tool started: %s | input: %s", tool_name, input_str)

    def on_tool_end(self, output, **kwargs):
        output_str = str(output)
        if len(output_str) > 300:
            output_str = output_str[:300] + "... (truncated)"
        logger.info("Tool completed: output=%s", output_str)

    def on_tool_error(self, error, **kwargs):
        logger.error("Tool failed: %s: %s", type(error).__name__, error)

    def on_llm_start(self, serialized, prompts, **kwargs):
        logger.info("LLM call started")

    def on_llm_end(self, response, **kwargs):
        logger.info("LLM call completed")

    def on_llm_error(self, error, **kwargs):
        logger.error("LLM call failed: %s: %s", type(error).__name__, error)
