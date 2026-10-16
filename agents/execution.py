"""Execution Engine — simulated trade execution and logging."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import settings
from models.schemas import ExecutionResult, FinalDecision
from utils.agent_health import tracked
from utils.logger import setup_logger

logger = setup_logger("execution")


class ExecutionEngine:
    """Simulated execution engine. Logs trades to a JSONL ledger."""

    name = "execution_engine"

    def run(self, context: dict[str, Any]) -> ExecutionResult:
        decision: FinalDecision = context["decision"]
        ticker = decision.ticker

        order_id = str(uuid.uuid4())[:8]

        if decision.action == "execute":
            status = "executed_simulated"
            details = (
                f"SIMULATED: {decision.action.upper()} {ticker} | "
                f"Entry: {decision.final_entry} | "
                f"SL: {decision.final_stop_loss} | "
                f"TP: {decision.final_take_profit} | "
                f"Size: {decision.final_position_size_pct}%"
            )
        elif decision.action == "hold":
            status = "held"
            details = f"HELD: No trade executed for {ticker}. Reason: {decision.reasoning}"
        else:
            status = "rejected"
            details = f"REJECTED: Trade for {ticker} rejected. Reason: {decision.reasoning}"

        result = ExecutionResult(
            agent_name=self.name,
            ticker=ticker,
            order_id=order_id,
            status=status,
            details=details,
            usage=context.get("usage"),
        )

        # Log to trades ledger
        self._log_trade(result)
        logger.info("[%s] %s", self.name, details)

        return result

    def _log_trade(self, result: ExecutionResult) -> None:
        log_path = Path(settings.TRADE_LOG_FILE)
        log_path.parent.mkdir(exist_ok=True)
        with open(log_path, "a") as f:
            f.write(result.model_dump_json() + "\n")


# Not an LLM agent, but a pipeline stage: record its outcome for the Agents page too
ExecutionEngine.run = tracked(ExecutionEngine.name, ExecutionEngine.run)
