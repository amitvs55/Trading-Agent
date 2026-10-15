"""Pipeline orchestrator — coordinates all 13 agents through 6 sequential stages."""

import concurrent.futures
import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from agents.bear_researcher import BearResearcherAgent
from agents.bull_researcher import BullResearcherAgent
from agents.execution import ExecutionEngine
from agents.fundamentals import FundamentalsAgent
from agents.market_data import MarketDataAgent
from agents.moderator import ModeratorAgent
from agents.news import NewsAgent
from agents.portfolio_manager import PortfolioManagerAgent
from agents.risk_aggressive import AggressiveRiskAgent
from agents.risk_conservative import ConservativeRiskAgent
from agents.risk_neutral import NeutralRiskAgent
from agents.sentiment import SentimentAgent
from agents.trader import TraderAgent
from config.settings import settings
from models.schemas import PipelineResult
from utils.logger import setup_logger

logger = setup_logger("pipeline")
console = Console()


class TradingPipeline:
    """Orchestrates the full trading analysis pipeline."""

    def __init__(self, ticker: str):
        self.ticker = ticker.upper()

        # Stage 1: Data Collection
        self.market_agent = MarketDataAgent()
        self.sentiment_agent = SentimentAgent()
        self.news_agent = NewsAgent()
        self.fundamentals_agent = FundamentalsAgent()

        # Stage 2: Research
        self.bull_agent = BullResearcherAgent()
        self.bear_agent = BearResearcherAgent()
        self.moderator_agent = ModeratorAgent()

        # Stage 3: Trading
        self.trader_agent = TraderAgent()

        # Stage 4: Risk Management
        self.risk_aggressive = AggressiveRiskAgent()
        self.risk_neutral = NeutralRiskAgent()
        self.risk_conservative = ConservativeRiskAgent()

        # Stage 5: Decision
        self.portfolio_manager = PortfolioManagerAgent()

        # Stage 6: Execution
        self.execution_engine = ExecutionEngine()

    def run(self) -> PipelineResult:
        """Run the full 6-stage pipeline."""
        start = time.time()

        console.print(Panel(
            f"[bold cyan]TradingAgents Pipeline[/bold cyan]\n"
            f"Ticker: [bold yellow]{self.ticker}[/bold yellow]",
            title="Starting Analysis",
        ))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            # ── Stage 1: Data Collection (parallel) ──
            task = progress.add_task("[cyan]Stage 1: Collecting market data...", total=None)
            analyst_outputs = self._stage_data_collection()
            progress.update(task, description="[green]Stage 1: Data collection complete")
            progress.remove_task(task)

            # ── Stage 2: Research (sequential) ──
            task = progress.add_task("[cyan]Stage 2: Running research debate...", total=None)
            bull, bear, verdict = self._stage_research(analyst_outputs)
            progress.update(task, description="[green]Stage 2: Research debate complete")
            progress.remove_task(task)

            # ── Stage 3: Trading ──
            task = progress.add_task("[cyan]Stage 3: Generating trade proposal...", total=None)
            proposal = self._stage_trading(verdict, analyst_outputs["market"])
            progress.update(task, description="[green]Stage 3: Trade proposal ready")
            progress.remove_task(task)

            # ── Stage 4: Risk Assessment (parallel) ──
            task = progress.add_task("[cyan]Stage 4: Risk assessment...", total=None)
            risk_assessments = self._stage_risk(proposal)
            progress.update(task, description="[green]Stage 4: Risk assessment complete")
            progress.remove_task(task)

            # ── Stage 5: Portfolio Decision ──
            task = progress.add_task("[cyan]Stage 5: Portfolio manager deciding...", total=None)
            decision = self._stage_decision(proposal, risk_assessments)
            progress.update(task, description="[green]Stage 5: Decision made")
            progress.remove_task(task)

            # ── Stage 6: Execution ──
            task = progress.add_task("[cyan]Stage 6: Executing...", total=None)
            execution = self._stage_execution(decision)
            progress.update(task, description="[green]Stage 6: Execution complete")
            progress.remove_task(task)

        elapsed = time.time() - start

        return PipelineResult(
            ticker=self.ticker,
            market_data=analyst_outputs["market"],
            sentiment=analyst_outputs["sentiment"],
            news=analyst_outputs["news"],
            fundamentals=analyst_outputs["fundamentals"],
            bull_case=bull,
            bear_case=bear,
            debate_verdict=verdict,
            trade_proposal=proposal,
            risk_assessments=risk_assessments,
            final_decision=decision,
            execution=execution,
            total_duration_seconds=round(elapsed, 1),
        )

    def _stage_data_collection(self) -> dict[str, Any]:
        """Stage 1: Run 4 data collection agents in parallel."""
        logger.info("Stage 1: Data collection for %s", self.ticker)
        ctx = {"ticker": self.ticker}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=settings.MAX_PARALLEL_WORKERS
        ) as pool:
            futures = {
                "market": pool.submit(self.market_agent.run, ctx),
                "sentiment": pool.submit(self.sentiment_agent.run, ctx),
                "news": pool.submit(self.news_agent.run, ctx),
                "fundamentals": pool.submit(self.fundamentals_agent.run, ctx),
            }
            results = {}
            for key, future in futures.items():
                try:
                    results[key] = future.result()
                    logger.info("Stage 1: %s complete", key)
                except Exception as e:
                    logger.error("Stage 1: %s failed: %s", key, e)
                    raise

        return results

    def _stage_research(self, analyst_outputs: dict) -> tuple:
        """Stage 2: Bull/Bear research + moderated debate."""
        logger.info("Stage 2: Research debate")
        context = {"ticker": self.ticker, **analyst_outputs}

        bull = self.bull_agent.run(context)
        bull.agent_name = "bull_researcher"
        bull.ticker = self.ticker

        bear = self.bear_agent.run(context)
        bear.agent_name = "bear_researcher"
        bear.ticker = self.ticker

        verdict = self.moderator_agent.run({
            "ticker": self.ticker,
            "bull": bull,
            "bear": bear,
        })
        verdict.agent_name = "debate_moderator"
        verdict.ticker = self.ticker

        return bull, bear, verdict

    def _stage_trading(self, verdict, market_data) -> Any:
        """Stage 3: Trader proposes a trade."""
        logger.info("Stage 3: Trade proposal")
        proposal = self.trader_agent.run({
            "ticker": self.ticker,
            "verdict": verdict,
            "market": market_data,
        })
        proposal.agent_name = "trader"
        proposal.ticker = self.ticker
        return proposal

    def _stage_risk(self, proposal) -> list:
        """Stage 4: Run 3 risk managers in parallel."""
        logger.info("Stage 4: Risk assessment")
        ctx = {"proposal": proposal}

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [
                pool.submit(self.risk_aggressive.run, ctx),
                pool.submit(self.risk_neutral.run, ctx),
                pool.submit(self.risk_conservative.run, ctx),
            ]
            results = []
            for f in futures:
                result = f.result()
                result.ticker = self.ticker
                results.append(result)

        return results

    def _stage_decision(self, proposal, risk_assessments) -> Any:
        """Stage 5: Portfolio manager makes final decision."""
        logger.info("Stage 5: Portfolio decision")
        decision = self.portfolio_manager.run({
            "ticker": self.ticker,
            "proposal": proposal,
            "risks": risk_assessments,
        })
        decision.agent_name = "portfolio_manager"
        decision.ticker = self.ticker
        return decision

    def _stage_execution(self, decision) -> Any:
        """Stage 6: Execute or log the decision."""
        logger.info("Stage 6: Execution")
        return self.execution_engine.run({"decision": decision})
