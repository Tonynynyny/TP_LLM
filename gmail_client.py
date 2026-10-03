import os
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from email import policy
from email.parser import BytesParser

from main import SCOPES

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

def get_message_body(service, message_id):
    """
    Récupère le corps du message à partir de son ID.
    """
    message = service.users().messages().get(userId="me", id=message_id, format="raw").execute()
    encoded_body = message["raw"]
    raw_body = base64.urlsafe_b64decode(encoded_body + "=" * (-len(encoded_body) % 4))
    mime_message = BytesParser(policy=policy.default).parsebytes(raw_body)
    part = mime_message.get_body(preferencelist=("plain",))
    body = part.get_content() if part is not None else None
    return body

service = authenticate_gmail()
ids = list_unread_message_ids(service)
print(f"IDs of unread messages: {ids}")
print(f"Body of the first unread message: {get_message_body(service, ids[0])}")