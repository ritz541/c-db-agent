from unittest.mock import MagicMock

from subscribers.console import ConsoleSubscriber
from core.events.domain import MessageSent
from core.models.message import AgentMessage


def test_console_subscriber_filters_non_assistant_roles():
    """Verify ConsoleSubscriber only renders Assistant panels for role == 'assistant'."""
    mock_console = MagicMock()
    subscriber = ConsoleSubscriber(console=mock_console)

    tool_msg = AgentMessage(role="tool", content='{"success": true, "rows": []}')
    subscriber.on_message_sent(MessageSent(message=tool_msg))
    mock_console.print.assert_not_called()

    system_msg = AgentMessage(role="system", content="System instruction")
    subscriber.on_message_sent(MessageSent(message=system_msg))
    mock_console.print.assert_not_called()

    assistant_msg = AgentMessage(role="assistant", content="Hello, world!")
    subscriber.on_message_sent(MessageSent(message=assistant_msg))
    assert mock_console.print.call_count == 1
