import asyncio
import sys
import structlog
from rich.console import Console

from agent.builder import Agent
from config.settings import get_settings
from infrastructure.db_pool import init_db_pool, get_connection, is_db_available
from runtime.middleware.logging import LoggingMiddleware
from runtime.middleware.timing import TimingMiddleware
from subscribers.console import ConsoleSubscriber
from subscribers.structlog_subscriber import StructlogSubscriber
from tools.registry import registry

logger = structlog.get_logger(__name__)


class CLIRunner:
    """CLI Runner UI Adapter decoupling CLI interaction from agent core."""

    def __init__(self) -> None:
        self.console = Console()
        self.settings = get_settings()

    async def run_prompt(self, agent: Agent, prompt: str) -> None:
        try:
            res = await agent.run(prompt)
            if res.final_output and not res.final_output.startswith("["):
                pass
        except Exception as e:
            self.console.print(f"[bold red]Execution error:[/bold red] {e}")

    async def start(self) -> None:
        self.console.print("[bold blue]🤖 Starting Agent Runtime Framework CLI...[/bold blue]")

        # Initialize DB pool
        try:
            if self.settings.cockroachdb_url:
                init_db_pool(
                    db_url=self.settings.cockroachdb_url,
                    minconn=self.settings.db_pool_minconn,
                    maxconn=self.settings.db_pool_maxconn,
                )
        except Exception as e:
            logger.warning("cli_runner.db_conn_warning", error=str(e))

        # Auto-discover tools
        registry.auto_discover()
        discovered_tools = [registry.get_tool(name) for name in registry.list_tools()]

        # Build Agent
        builder = (
            Agent.builder()
            .with_llm(self.settings.llm_model)
            .with_subscriber(ConsoleSubscriber(console=self.console))
            .with_subscriber(StructlogSubscriber())
            .with_middleware(TimingMiddleware())
            .with_middleware(LoggingMiddleware())
        )

        for tool in discovered_tools:
            if tool:
                builder.with_tool(tool)

        agent = builder.build()
        self.console.print(f"[green]✔ Agent runtime ready with {len(discovered_tools)} tools.[/green]")
        self.console.print("[dim]Type your prompt below. Type 'exit', 'quit', or 'q' to quit.[/dim]\n")

        while True:
            try:
                user_input = input("user > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    self.console.print("[yellow]Goodbye![/yellow]")
                    break

                await self.run_prompt(agent, user_input)
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[yellow]Exiting CLI runner...[/yellow]")
                break
