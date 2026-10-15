"""TradingAgents — Multi-Agent Trading System CLI.

Usage:
    python main.py AAPL
    python main.py TSLA --verbose

Disclaimer: This system is for research purposes only. Not financial advice.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import settings
from orchestrator.pipeline import TradingPipeline

app = typer.Typer(
    name="tradingagents",
    help="Multi-Agent LLM-powered Trading Analysis System",
)
console = Console()


def _display_results(result) -> None:
    """Display pipeline results using Rich tables and panels."""

    # ── Market Data ──
    md = result.market_data
    console.print(Panel(
        f"Price: [bold]{md.current_price}[/bold]  "
        f"1D: {md.price_change_pct_1d:+.2f}%  "
        f"5D: {md.price_change_pct_5d:+.2f}%  "
        f"Signal: [bold]{md.trend_signal.upper()}[/bold]\n"
        f"RSI: {md.indicators.rsi_14}  "
        f"MACD: {md.indicators.macd_histogram}  "
        f"Volume: {md.volume:,}" if md.volume else "",
        title="[cyan]Market Data[/cyan]",
    ))

    # ── Sentiment ──
    console.print(Panel(
        f"Overall: [bold]{result.sentiment.overall_score:+.2f}[/bold]  "
        f"Twitter: {result.sentiment.twitter_score}  "
        f"Reddit: {result.sentiment.reddit_score}\n"
        f"Source: {result.sentiment.data_source}\n"
        f"{result.sentiment.summary[:200]}",
        title="[cyan]Sentiment[/cyan]",
    ))

    # ── Research Debate ──
    v = result.debate_verdict
    table = Table(title="Research Debate")
    table.add_column("Side", style="bold")
    table.add_column("Score", justify="center")
    table.add_column("Confidence", justify="center")
    table.add_column("Key Argument")
    table.add_row(
        "[green]BULL[/green]",
        f"{v.bull_score:.1f}/10",
        f"{result.bull_case.confidence:.0%}",
        result.bull_case.key_arguments[0] if result.bull_case.key_arguments else "N/A",
    )
    table.add_row(
        "[red]BEAR[/red]",
        f"{v.bear_score:.1f}/10",
        f"{result.bear_case.confidence:.0%}",
        result.bear_case.key_arguments[0] if result.bear_case.key_arguments else "N/A",
    )
    console.print(table)
    console.print(f"  Verdict: [bold]{v.final_recommendation.upper()}[/bold] (Winner: {v.winner})")

    # ── Trade Proposal ──
    tp = result.trade_proposal
    console.print(Panel(
        f"Direction: [bold]{tp.direction.value.upper()}[/bold]  "
        f"Entry: {tp.entry_price}  "
        f"SL: {tp.stop_loss}  "
        f"TP: {tp.take_profit}\n"
        f"Size: {tp.position_size_pct:.1f}%  "
        f"R:R: {tp.risk_reward_ratio}  "
        f"Horizon: {tp.time_horizon}",
        title="[cyan]Trade Proposal[/cyan]",
    ))

    # ── Risk Assessments ──
    risk_table = Table(title="Risk Assessments")
    risk_table.add_column("Profile", style="bold")
    risk_table.add_column("Approve", justify="center")
    risk_table.add_column("Risk Score", justify="center")
    risk_table.add_column("Max Size", justify="center")
    risk_table.add_column("Top Concern")
    for ra in result.risk_assessments:
        approve_str = "[green]YES[/green]" if ra.approve else "[red]NO[/red]"
        risk_table.add_row(
            ra.profile.value.upper(),
            approve_str,
            f"{ra.risk_score:.1f}/10",
            f"{ra.max_position_size_pct:.1f}%",
            ra.concerns[0] if ra.concerns else "None",
        )
    console.print(risk_table)

    # ── Final Decision ──
    fd = result.final_decision
    action_colors = {"execute": "green", "hold": "yellow", "reject": "red"}
    color = action_colors.get(fd.action, "white")
    console.print(Panel(
        f"Action: [bold {color}]{fd.action.upper()}[/bold {color}]\n"
        f"Entry: {fd.final_entry}  SL: {fd.final_stop_loss}  "
        f"TP: {fd.final_take_profit}  Size: {fd.final_position_size_pct}%\n"
        f"Reasoning: {fd.reasoning[:300]}",
        title="[cyan]Portfolio Manager Decision[/cyan]",
    ))

    # ── Execution ──
    ex = result.execution
    console.print(Panel(
        f"Order ID: {ex.order_id}  Status: [bold]{ex.status}[/bold]\n{ex.details}",
        title="[cyan]Execution[/cyan]",
    ))

    console.print(f"\n[dim]Total pipeline time: {result.total_duration_seconds:.1f}s[/dim]")


@app.command()
def analyze(
    ticker: str = typer.Argument(..., help="Stock ticker symbol (e.g., AAPL, TSLA, MSFT)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save full JSON output"),
):
    """Run the full TradingAgents pipeline for a given stock ticker."""

    # Validate API key
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.startswith("sk-your"):
        console.print(
            "[red]Error: OPENAI_API_KEY not set.[/red]\n"
            "Copy .env.example to .env and add your OpenAI API key.",
            style="bold",
        )
        raise typer.Exit(1)

    console.print(
        Panel(
            "[bold]TradingAgents[/bold] - Multi-Agent Trading Analysis\n"
            "[dim]Disclaimer: For research purposes only. Not financial advice.[/dim]",
            style="blue",
        )
    )

    try:
        pipeline = TradingPipeline(ticker)
        result = pipeline.run()

        console.print("\n")
        _display_results(result)

        # Save JSON output
        if save:
            data_dir = Path(settings.DATA_DIR)
            data_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = data_dir / f"{ticker.upper()}_{ts}.json"
            output_path.write_text(result.model_dump_json(indent=2))
            console.print(f"\n[dim]Full output saved to {output_path}[/dim]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted by user.[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"\n[red]Pipeline error: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
