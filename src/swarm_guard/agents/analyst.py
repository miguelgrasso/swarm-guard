"""Analyst agent — analyses researcher output and hands off to Writer."""

from __future__ import annotations

from typing import Any

from strands import Agent
from strands.models.model import Model
from strands.tools.decorator import tool


@tool
def analyze_data(data: str) -> str:
    """Analyse the provided data and return a structured analysis (read-only).

    Args:
        data: Raw research data or text to analyse.

    Returns:
        Structured analysis with key patterns and insights.
    """
    length = len(data)
    msg = f"Input length: {length} chars."
    return f"Analysis of input data: identified key patterns and insights. {msg}"


_SYSTEM_PROMPT = """\
You are an Analyst agent. Your role is to analyse the research findings provided by the
Researcher agent using the analyze_data tool.

When you have completed your analysis:
- Produce a structured summary of patterns, risks, and recommendations.
- Hand off control to the 'writer' agent by calling handoff_to_agent with your analysis.

Do NOT produce a final answer yourself — always hand off to the writer.
"""


def build_analyst(model: Model) -> Agent:
    """Build and return the Analyst agent.

    Args:
        model: The model backend to use for inference.

    Returns:
        Configured Analyst Agent ready to be added to a Swarm.
    """
    return Agent(
        model=model,
        system_prompt=_SYSTEM_PROMPT,
        tools=[analyze_data],
        name="analyst",
        description="Analyses research data and hands off to the writer.",
    )


class Analyst:
    """Convenience wrapper that constructs an Analyst Agent from a model."""

    def __init__(self, model: Model) -> None:
        self.agent: Agent = build_analyst(model)

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying Agent."""
        return getattr(self.agent, name)
