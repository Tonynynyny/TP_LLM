import json
import os
import tempfile

STATE_FILE = "state.json"

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        raise ValueError("Fichier d'état illisible ou corrompu. Blocage par sécurité.")

def save_state(state_data: dict):
    """Sauvegarde l'état via un remplacement atomique."""
    directory = os.path.dirname(os.path.abspath(STATE_FILE)) if os.path.exists(STATE_FILE) else "."
    fd, temp_path = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding="utf-8") as f:
            json.dump(state_data, f, indent=4)
        os.replace(temp_path, STATE_FILE)
    except Exception as e:
        os.remove(temp_path)
        raise e

def get_status(gmail_id: str) -> str | None:
    return load_state().get(gmail_id)

def update_status(gmail_id: str, status: str):
    state = load_state()
    state[gmail_id] = status
    save_state(state)