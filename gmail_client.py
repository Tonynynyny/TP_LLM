import os
import base64
from dataclasses import dataclass
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from email import policy
from email.parser import BytesParser
from email.message import EmailMessage
from email.utils import getaddresses

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


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
    auto_submitted: str | None
    list_id: str | None


def authenticate_gmail():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        open("token.json", "w").write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def list_unread_message_ids(service, limit=10):
    """
    Lists the IDs of unread messages in the user's inbox.
    """
    # Demande à Gmail les messages portant le libellé « non lu ».
    results = service.users().messages().list(userId="me", labelIds=["UNREAD"], maxResults=limit).execute()

    # Récupère la liste renvoyée, ou une liste vide s'il n'y a aucun message.
    messages = results.get("messages", [])
    return [msg["id"] for msg in messages]


def fetch_incoming_email(service, gmail_id) -> IncomingEmail:
    def _get_header(mime, name):
        value = mime[name]
        return str(value) if value is not None else None

    
    res = service.users().messages().get(
        userId="me", id=gmail_id, format="raw"
    ).execute(num_retries=3)
    encoded = res["raw"]
    raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    mime = BytesParser(policy=policy.default).parsebytes(raw)
    part = mime.get_body(preferencelist=("plain",))
    try:
        body = part.get_content() if part is not None else None
    except (LookupError, UnicodeDecodeError):   # charset exotique
        body = None
    return IncomingEmail(
        gmail_id=gmail_id, thread_id=res["threadId"],
        message_id_header=_get_header(mime, "Message-ID"), references=_get_header(mime, "References"),
        from_header=_get_header(mime, "From"), reply_to_header=_get_header(mime, "Reply-To"),
        subject=_get_header(mime, "Subject"), body=body,
        auto_submitted=_get_header(mime, "Auto-Submitted"), list_id=_get_header(mime, "List-Id"),
    )



def select_recipient(incoming: IncomingEmail) -> str:
    """Reply-To si présent, sinon From. Une seule adresse valide."""
    raw = incoming.reply_to_header if incoming.reply_to_header is not None else incoming.from_header
    if not raw:
        raise ValueError("aucun expéditeur")
    addresses = getaddresses([raw])
    if len(addresses) != 1:
        raise ValueError("destinataire ambigu")
    address = addresses[0][1].strip().lower()
    if "@" not in address or any(c in address for c in "\r\n\t <>,;"):
        raise ValueError("adresse invalide")
    return address


def build_reply_mime(incoming: IncomingEmail, reply_body: str,
                     own_address: str) -> bytes:
    if not reply_body or not reply_body.strip():
        raise ValueError("corps de réponse vide")
    if not incoming.message_id_header:
        raise ValueError("Message-ID source absent")

    msg = EmailMessage()
    msg["From"] = own_address
    msg["To"] = select_recipient(incoming)
    msg["Subject"] = incoming.subject or ""          # sujet original, sans "Re:"
    msg["In-Reply-To"] = incoming.message_id_header
    refs = (incoming.references or "").split()
    if incoming.message_id_header not in refs:
        refs.append(incoming.message_id_header)
    msg["References"] = " ".join(refs)
    msg.set_content(reply_body)
    return msg.as_bytes()

def create_draft(service, mime_bytes, thread_id):
    """Crée un brouillon Gmail à partir d'un MIMEText dans le thread indiqué."""
    encoded = base64.urlsafe_b64encode(mime_bytes).decode("ascii")
    result = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": encoded, "threadId": thread_id}},
    ).execute()
    return result["id"]

if __name__ == "__main__":
    service = authenticate_gmail()
    owner_address = service.users().getProfile(userId="me").execute()["emailAddress"]
    ids = list_unread_message_ids(service, limit=5)
    print(f"IDs : {ids}")
    if ids:
        incoming = fetch_incoming_email(service, ids[1])
        mime_bytes = build_reply_mime(
            incoming,
            "Merci pour votre message. Je vous répondrai dès que possible.",
            owner_address,
        )
        print(create_draft(service, mime_bytes, incoming.thread_id))