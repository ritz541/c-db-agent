#!/usr/bin/env python3
"""
Agent Runtime Framework - Top Level Entry Point
"""

import asyncio
from agent.builder import Agent, AgentBuilder
from ui.cli.runner import CLIRunner

__all__ = ["Agent", "AgentBuilder"]


def main() -> None:
    runner = CLIRunner()
    try:
        asyncio.run(runner.start())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
