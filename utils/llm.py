"""OpenAI API wrapper with retry logic and JSON output."""

import json
import time
from typing import Any

from openai import OpenAI, BadRequestError
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from utils.helpers import parse_json_response
from utils.logger import setup_logger

logger = setup_logger("llm")

# Models known to support response_format=json_object
JSON_MODE_MODELS = {
    "gpt-4-turbo", "gpt-4-turbo-preview", "gpt-4-turbo-2024-04-09",
    "gpt-4o", "gpt-4o-mini", "gpt-4o-2024-05-13", "gpt-4o-2024-08-06",
    "gpt-4o-mini-2024-07-18", "gpt-3.5-turbo-0125", "gpt-3.5-turbo-1106",
}


class LLMClient:
    """Wrapper around OpenAI chat completions with retry and JSON output."""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.MODEL_NAME
        self.temperature = settings.LLM_TEMPERATURE
        self._supports_json_mode = None

    def _check_json_mode_support(self) -> bool:
        """Check if the configured model supports response_format=json_object."""
        if self._supports_json_mode is not None:
            return self._supports_json_mode
        # Check known models, and also allow any model containing these substrings
        model_lower = self.model.lower()
        self._supports_json_mode = (
            self.model in JSON_MODE_MODELS
            or "turbo" in model_lower
            or "gpt-4o" in model_lower
            or "gpt-3.5-turbo-0125" in model_lower
        )
        return self._supports_json_mode

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Call OpenAI and return parsed JSON dict.

        Tries response_format=json_object first. If the model doesn't support it,
        falls back to prompt-based JSON extraction.
        """
        temp = temperature if temperature is not None else self.temperature
        start = time.time()

        # Build request kwargs
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temp,
        )

        # Try JSON mode if supported
        if self._check_json_mode_support():
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**kwargs)
        except BadRequestError as e:
            if "response_format" in str(e) and "json_object" in str(e):
                # Model doesn't support JSON mode — fall back
                logger.warning("Model %s doesn't support JSON mode, falling back to prompt-based JSON", self.model)
                self._supports_json_mode = False
                kwargs.pop("response_format", None)
                response = self.client.chat.completions.create(**kwargs)
            else:
                raise

        elapsed = time.time() - start
        usage = response.usage
        logger.info(
            "LLM call: model=%s tokens=%d (prompt=%d, completion=%d) time=%.1fs",
            self.model,
            usage.total_tokens if usage else 0,
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
            elapsed,
        )

        content = response.choices[0].message.content or "{}"
        return parse_json_response(content)
