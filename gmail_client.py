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

from models import IncomingEmail
from validation import validate_recipient

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


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


    
def list_unread_message_ids(service, limit=5):
    SEARCH_QUERY = "in:inbox is:unread subject:TP-LLM -in:sent -in:drafts"

    if limit <= 0:
        return []

    message_ids = []
    page_token = None
    while len(message_ids) < limit:
        request = service.users().messages().list(
            userId="me",
            q=SEARCH_QUERY,
            maxResults=limit - len(message_ids),
            includeSpamTrash=False,
            **({"pageToken": page_token} if page_token else {}),
        )
        page = request.execute(num_retries=3)
        message_ids.extend(m["id"] for m in page.get("messages", []))
        page_token = page.get("nextPageToken")
        if not page_token:
            break

    return message_ids[:limit]


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
        if body is not None and not isinstance(body, str):
            body = None
    except (KeyError, LookupError, UnicodeDecodeError):   # charset ou structure exotique
        body = None

    message_id = _get_header(mime, "Message-ID")
    from_header = _get_header(mime, "From")
    subject = _get_header(mime, "Subject")
    if body is None:
        raise ValueError("corps du message absent ou illisible")
    if len(body) > 12000:
        raise ValueError("message rejeté : corps supérieur à 12 000 caractères")
    if not message_id or not from_header or not subject:
        raise ValueError("message rejeté : en-tête obligatoire absent")

    auto_submitted = (_get_header(mime, "Auto-Submitted") or "").strip().lower()
    precedence = (_get_header(mime, "Precedence") or "").strip().lower()
    list_id = _get_header(mime, "List-Id")

    if (auto_submitted and auto_submitted != "no") or precedence in {"bulk", "list", "junk"} or list_id is not None:
        raise ValueError("message rejeté : message automatique")

    return IncomingEmail(
        gmail_id=gmail_id, thread_id=res["threadId"],
        message_id_header=message_id, references=_get_header(mime, "References"),
        from_header=from_header, reply_to_header=_get_header(mime, "Reply-To"),
        subject=subject, body=body,
    )


def build_reply_mime(incoming: IncomingEmail, reply_body: str,
                     own_address: str) -> bytes:
    if not reply_body or not reply_body.strip():
        raise ValueError("corps de réponse vide")
    if not incoming.message_id_header:
        raise ValueError("Message-ID source absent")

    msg = EmailMessage()
    msg["From"] = own_address
    msg["To"] = validate_recipient(incoming)
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
    ).execute(num_retries=3)
    return result["id"]

if __name__ == "__main__":
    service = authenticate_gmail()
    owner_address = service.users().getProfile(userId="me").execute(num_retries=3)["emailAddress"]
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