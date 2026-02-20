"""Mock email service — logs styled email previews."""

import sys
from datetime import datetime, timezone


class MockEmailService:
    """Simulated email service that renders styled email previews to logs."""

    @staticmethod
    def send(
        to: str,
        subject: str,
        body: str,
        email_type: str,
        metadata: dict | None = None,
    ) -> dict:
        meta = metadata or {}
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        body_lines = body.strip().split("\n")
        formatted_body = "\n".join(f"  │  {line:<56} │" for line in body_lines)

        output = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  SMARTCOURSE EMAIL SERVICE (MOCK)                    {timestamp}  ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃  To:       {to:<55} ┃
┃  Subject:  {subject:<55} ┃
┃  Type:     {email_type:<55} ┃
┃                                                                    ┃
┃  Body:                                                             ┃
┃  ┌──────────────────────────────────────────────────────────────┐  ┃
{formatted_body}
┃  └──────────────────────────────────────────────────────────────┘  ┃
┃                                                                    ┃
┃  Status:   DELIVERED (mock)                                        ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"""

        print(output, file=sys.stderr, flush=True)
        return {"status": "delivered_mock", "to": to, "type": email_type, **meta}
