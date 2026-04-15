"""Midas agents — LLM-powered analyst, debate, and research agents.

Provides frontier LLM provider abstraction and three specialist agents:
- AnalystAgent: produces structured briefs from decision context
- DebateAgent: steelman/red-team structured debate
- ResearchAgent: RAG-based research assistant

Plus supporting infrastructure:
- FrontierProvider: OpenAI-compatible API with fallback
- DebateTools: 10 MCP tools for the debate agent
- AgentOrchestrator: coordinates the full decision pipeline
"""

from midas.agents.analyst import AnalystAgent
from midas.agents.debate import DebateAgent
from midas.agents.orchestrator import AgentOrchestrator
from midas.agents.provider import FrontierProvider
from midas.agents.research import ResearchAgent
from midas.agents.tools import DebateTools

__all__ = [
    "AnalystAgent",
    "DebateAgent",
    "DebateTools",
    "FrontierProvider",
    "AgentOrchestrator",
    "ResearchAgent",
]
