from email.utils import getaddresses
from models import IncomingEmail

# Liste d'adresses de test autorisées pour le TP (à adapter selon vos adresses de test)
APPROVED_RECIPIENTS = [
    "jeftranquille@gmail.com",
    "aaitouaret37@gmail.com",
]

def validate_recipient(incoming: IncomingEmail, allowed_addresses: list[str] = APPROVED_RECIPIENTS) -> str:
    """
    Extrait et valide l'adresse du destinataire selon les règles du TP :
    - Sélectionne Reply-To si présent, sinon From.
    - Refuse si aucune adresse ou si ambigu (plusieurs adresses).
    - Vérifie la conformité du format.
    - Vérifie que l'adresse appartient à la liste autorisée.
    """
    raw = incoming.reply_to_header if incoming.reply_to_header else incoming.from_header
    if not raw:
        raise ValueError("Aucun expéditeur trouvé (en-tête From et Reply-To absents).")

    addresses = getaddresses([raw])
    if len(addresses) != 1:
        raise ValueError(f"En-tête destinataire ambigu ({len(addresses)} adresses trouvées).")

    _, address = addresses[0]
    address = address.strip().lower()

    if not address or "@" not in address or any(c in address for c in "\r\n\t <>,;"):
        raise ValueError(f"Adresse destinataire invalide : {address}")

    if allowed_addresses and address not in [a.lower() for a in allowed_addresses]:
        raise ValueError(f"Adresse non autorisée (hors liste blanche) : {address}")

    return address