"""OpenAI API wrapper: one retry layer, JSON output, and a record of every call.

Reproducibility (review finding F-16): temperature 0 and a fixed seed by default, a dated model
snapshot, and when the pipeline hands over a `call_log`, the full prompt and answer of each call
with the snapshot the API actually used, so a research decision can be audited and replayed.

Retries: only transport problems (timeouts, connection errors, 429 rate limits, 5xx) are retried,
here and nowhere else; the SDK's own retries are off. Before this, SDK × tenacity × the agent's
validation retry could add up to 18 attempts for one call.
"""

import time
from datetime import datetime, timezone
from typing import Any

import openai
from openai import BadRequestError, OpenAI
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config.settings import settings
from utils.helpers import parse_json_response
from utils.logger import setup_logger
from utils.usage import UsageTracker

logger = setup_logger("llm")

# Models known to support response_format=json_object
JSON_MODE_MODELS = {
    "gpt-4-turbo", "gpt-4-turbo-preview", "gpt-4-turbo-2024-04-09",
    "gpt-4o", "gpt-4o-mini", "gpt-4o-2024-05-13", "gpt-4o-2024-08-06",
    "gpt-4o-mini-2024-07-18", "gpt-3.5-turbo-0125", "gpt-3.5-turbo-1106",
}


def _transient(exc: BaseException) -> bool:
    if isinstance(exc, openai.RateLimitError):
        return "insufficient_quota" not in str(exc)          # out of credit: retrying can't help
    return isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError))


class LLMClient:
    """Wrapper around OpenAI chat completions with retry and JSON output."""

    def __init__(self, agent_name: str = "unknown"):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.LLM_TIMEOUT_S, max_retries=0)
        self.model = settings.MODEL_NAME
        self.temperature = settings.LLM_TEMPERATURE
        self.seed: int | None = settings.LLM_SEED
        self._supports_json_mode = None
        self.agent_name = agent_name
        # Set by the pipeline so each run gets its own tracker and call log
        self.tracker: UsageTracker | None = None
        self.call_log: list[dict] | None = None

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
        retry=retry_if_exception(_transient),
        stop=stop_after_attempt(max(1, settings.LLM_MAX_RETRIES)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        is_retry: bool = False,
    ) -> dict[str, Any]:
        """Call OpenAI and return parsed JSON dict.

        Tries response_format=json_object first. If the model doesn't support it,
        falls back to prompt-based JSON extraction.
        """
        temp = temperature if temperature is not None else self.temperature
        start = time.time()

        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temp,
        )
        if self.seed is not None:
            kwargs["seed"] = self.seed
        if self._check_json_mode_support():
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(**kwargs)
        except BadRequestError as e:
            if "response_format" in str(e) and "json_object" in str(e):
                logger.warning("Model %s doesn't support JSON mode, falling back to prompt-based JSON", self.model)
                self._supports_json_mode = False
                kwargs.pop("response_format", None)
                response = self.client.chat.completions.create(**kwargs)
            else:
                raise

        elapsed = time.time() - start
        usage = response.usage
        resolved = getattr(response, "model", None)
        resolved = resolved if isinstance(resolved, str) and resolved else self.model
        logger.info(
            "LLM call: agent=%s model=%s tokens=%d (prompt=%d, completion=%d) time=%.1fs",
            self.agent_name, resolved,
            usage.total_tokens if usage else 0,
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
            elapsed,
        )

        if self.tracker is not None and usage is not None:
            details = getattr(usage, "prompt_tokens_details", None)
            cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
            self.tracker.record(
                agent=self.agent_name,
                model=resolved,
                prompt_tokens=usage.prompt_tokens or 0,
                completion_tokens=usage.completion_tokens or 0,
                cached_tokens=cached,
                latency_s=elapsed,
                is_retry=is_retry,
            )

        content = response.choices[0].message.content or "{}"
        if self.call_log is not None:
            self.call_log.append({
                "ts": datetime.now(timezone.utc), "agent": self.agent_name, "model": resolved,
                "temperature": temp, "seed": kwargs.get("seed"), "system_prompt": system_prompt,
                "user_prompt": user_prompt, "response": content,
                "prompt_tokens": (usage.prompt_tokens or 0) if usage else None,
                "completion_tokens": (usage.completion_tokens or 0) if usage else None,
                "is_retry": int(is_retry),
            })
        return parse_json_response(content)
