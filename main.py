import argparse
from gmail_client import authenticate_gmail, list_unread_message_ids, fetch_incoming_email, build_reply_mime, create_draft
from LLM_client import generate_reply
from validation import validate_proposal
from state import get_status, update_status, load_state

def main():
    parser = argparse.ArgumentParser(description="Assistant Gmail avec LLM")
    parser.add_argument("--limit", type=int, default=5, help="Nombre max de courriels (défaut: 5)")
    parser.add_argument("--create-drafts", action="store_true", help="Autorise la création des brouillons")
    args = parser.parse_args()

    # Vérification anti-corruption de l'état
    try:
        load_state()
    except ValueError as e:
        print(f"Erreur fatale: {e}")
        return

    print("Authentification en cours...")
    service = authenticate_gmail()
    owner_address = service.users().getProfile(userId="me").execute(num_retries=3)["emailAddress"]

    message_ids = list_unread_message_ids(service, limit=args.limit)
    if not message_ids:
        print("Aucun message éligible trouvé.")
        return

    for gmail_id in message_ids:
        print(f"\n--- Traitement de {gmail_id} ---")
        
        status = get_status(gmail_id)
        if status in ["no_reply", "pending", "draft_created"]:
            print(f"Ignoré (déjà traité, statut: {status})")
            continue

        try:
            incoming = fetch_incoming_email(service, gmail_id)
            print(f"Sujet : {incoming.subject}")

            raw_json = generate_reply(incoming)
            proposal = validate_proposal(raw_json)

            if not proposal.needs_reply:
                print(f"Le LLM indique de ne pas répondre. Motif : {proposal.reason}")
                if args.create_drafts:
                    update_status(gmail_id, "no_reply")
                continue

            print("\n[ APERÇU ]")
            print(f"Destinataire : {incoming.reply_to_header or incoming.from_header}")
            print(f"Proposition  :\n{proposal.draft}\n")

            if args.create_drafts:
                rep = input("Créer ce brouillon dans Gmail ? (o/N) : ")
                if rep.lower() == 'o':
                    update_status(gmail_id, "pending")
                    
                    mime_bytes = build_reply_mime(incoming, proposal.draft, owner_address)
                    draft_id = create_draft(service, mime_bytes, incoming.thread_id)
                    
                    update_status(gmail_id, "draft_created")
                    print(f"-> Brouillon créé (ID: {draft_id})")
                else:
                    print("-> Annulé par l'utilisateur.")
            else:
                print("-> Mode aperçu : aucune écriture effectuée.")

        except Exception as e:
            print(f"Erreur sur le message {gmail_id} : {e}")

if __name__ == "__main__":
    main()