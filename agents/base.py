"""Base agent class with shared LLM call, parse, and validate logic."""

import json
from typing import Any, Type, TypeVar

from pydantic import BaseModel, ValidationError

from utils.agent_health import tracked
from utils.llm import LLMClient
from utils.logger import setup_logger

T = TypeVar("T", bound=BaseModel)

logger = setup_logger("agent")


class BaseAgent:
    """Base class for all LLM-powered agents.

    Subclasses set name, system_prompt, and output_model,
    then override build_user_prompt() to format their input context.
    """

    name: str = "base_agent"
    system_prompt: str = ""
    output_model: Type[BaseModel] = BaseModel

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Record every agent's outcome for the Agents page, including subclasses that override run()
        if "run" in cls.__dict__ and not getattr(cls.__dict__["run"], "__agent_tracked__", False):
            cls.run = tracked(cls.name, cls.__dict__["run"])
        elif "run" not in cls.__dict__:
            cls.run = tracked(cls.name, BaseAgent.__dict__["run"])

    def __init__(self):
        self.llm = LLMClient(agent_name=self.name)

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        """Build the user prompt from the input context. Override in subclasses."""
        return json.dumps(context, indent=2, default=str)

    def run(self, context: dict[str, Any]) -> BaseModel:
        """Execute the agent: build prompt → call LLM → validate output."""
        user_prompt = self.build_user_prompt(context)

        # Inject output schema into system prompt
        schema_json = json.dumps(
            self.output_model.model_json_schema(), indent=2
        )
        system = (
            f"{self.system_prompt}\n\n"
            f"You MUST respond with valid JSON matching this schema:\n{schema_json}"
        )

        logger.info("[%s] Running for context keys: %s", self.name, list(context.keys()))

        # First attempt
        try:
            raw = self.llm.call(system, user_prompt)
            result = self.output_model.model_validate(raw)
            logger.info("[%s] Output validated successfully", self.name)
            return result
        except (ValidationError, Exception) as e:
            logger.warning("[%s] First attempt failed: %s. Retrying with feedback.", self.name, e)

        # Retry with error feedback
        retry_prompt = (
            f"{user_prompt}\n\n"
            f"IMPORTANT: Your previous response had an error: {e}\n"
            f"Please fix the JSON output to match the required schema exactly."
        )
        raw = self.llm.call(system, retry_prompt, is_retry=True)
        result = self.output_model.model_validate(raw)
        logger.info("[%s] Output validated on retry", self.name)
        return result
