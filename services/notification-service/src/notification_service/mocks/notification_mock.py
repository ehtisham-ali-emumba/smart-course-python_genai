"""Mock in-app notification service — logs styled notification cards."""

import sys
import textwrap
from datetime import datetime, timezone


class MockNotificationService:
    """Simulated in-app notification service that renders styled cards to logs."""

    @staticmethod
    def create(
        user_id: int,
        title: str,
        message: str,
        notification_type: str = "system",
    ) -> dict:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        tag = notification_type.upper()

        wrapped = textwrap.wrap(message, width=53)
        msg_lines = []
        for i, line in enumerate(wrapped):
            prefix = "Message:  " if i == 0 else "          "
            msg_lines.append(f"   {prefix}{line:<53}")

        msg_block = "\n".join(f"║{line} ║" for line in msg_lines)

        output = f"""
╔══════════════════════════════════════════════════════════════════════╗
║  SMARTCOURSE NOTIFICATION SERVICE (MOCK)       {timestamp}  ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║   [ {tag:<60} ] ║
║                                                                    ║
║   User ID:  {user_id:<55}║
║   Title:    {title:<55}║
{msg_block}
║                                                                    ║
║   Channel:  IN_APP                                                 ║
║   Status:   CREATED (mock -- would write to notifications table)   ║
║                                                                    ║
╚══════════════════════════════════════════════════════════════════════╝"""

        print(output, file=sys.stderr, flush=True)
        return {
            "status": "created_mock",
            "user_id": user_id,
            "type": notification_type,
            "title": title,
        }
