"""Researcher agent — reads information and hands off to Analyst."""

from __future__ import annotations

from typing import Any

from strands import Agent
from strands.models.model import Model
from strands.tools.decorator import tool


@tool
def search_knowledge_base(query: str) -> str:
    """Search the knowledge base for information on the given query (read-only).

    Args:
        query: Topic or question to research.

    Returns:
        Structured summary of findings.
    """
    return f"Knowledge base results for '{query}': [synthetic research data]"


_SYSTEM_PROMPT = """\
You are a Researcher agent. Your role is to gather factual information about the topic
provided by the user using the search_knowledge_base tool.

When you have completed your research:
- Summarise your findings clearly.
- Hand off control to the 'analyst' agent by calling handoff_to_agent with your summary.

Do NOT produce a final answer yourself — always hand off to the analyst.
"""


def build_researcher(model: Model) -> Agent:
    """Build and return the Researcher agent.

    Args:
        model: The model backend to use for inference.

    Returns:
        Configured Researcher Agent ready to be added to a Swarm.
    """
    return Agent(
        model=model,
        system_prompt=_SYSTEM_PROMPT,
        tools=[search_knowledge_base],
        name="researcher",
        description="Gathers factual information and hands off to the analyst.",
    )


# ---------------------------------------------------------------------------
# Convenience class alias used by __init__.py exports
# ---------------------------------------------------------------------------


class Researcher:
    """Convenience wrapper that constructs a Researcher Agent from a model.

    Usage::

        researcher = Researcher(model=model)
        # researcher.agent is the strands.Agent instance
    """

    def __init__(self, model: Model) -> None:
        self.agent: Agent = build_researcher(model)

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying Agent."""
        return getattr(self.agent, name)
