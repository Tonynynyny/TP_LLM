from dataclasses import dataclass


@dataclass
class IncomingEmail:
    gmail_id: str
    thread_id: str
    message_id_header: str | None
    references: str | None
    from_header: str | None
    reply_to_header: str | None
    subject: str | None
    body: str | None
