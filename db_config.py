import os, json, sys
from pathlib import Path
from getpass import getpass

def _config_path() -> Path:
    # Load from the same folder as this script, in ./neo4j_app/credentials.json
    base = Path(__file__).resolve().parent
    return (base / "neo4j_app" / "credentials.json")

def _load_saved():
    p = _config_path()
    if p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return (data.get("uri"), data.get("user"), data.get("password"))
        except Exception:
            return (None, None, None)
    return (None, None, None)

# 1) Try env
NEO4J_URI  = (os.getenv("NEO4J_URI")  or "").strip()
NEO4J_USER = (os.getenv("NEO4J_USER") or "").strip()
NEO4J_PASSWORD = (os.getenv("NEO4J_PASSWORD") or "").strip()

# 2) If missing, try saved file
if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
    f_uri, f_user, f_pwd = _load_saved()
    if NEO4J_URI == "" and f_uri:  NEO4J_URI = f_uri.strip()
    if NEO4J_USER == "" and f_user: NEO4J_USER = f_user.strip()
    if NEO4J_PASSWORD == "" and f_pwd: NEO4J_PASSWORD = str(f_pwd).strip()

# 3) If still missing and interactive, prompt
def _prompt_if_missing():
    global NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    def prompt(msg, default=None, secret=False):
        if secret:
            return getpass(msg + (f" [{default}]" if default else "") + ": ")
        else:
            v = input(msg + (f" [{default}]" if default else "") + ": ").strip()
            return v or (default or "")
    if not sys.stdin or not sys.stdin.isatty():
        return
    if not NEO4J_URI:
        NEO4J_URI = prompt("Neo4j URI (bolt/neo4j/neo4j+s)", "bolt://localhost:7687").strip()
    if not NEO4J_USER:
        NEO4J_USER = prompt("Neo4j user", "neo4j").strip()
    if not NEO4J_PASSWORD:
        NEO4J_PASSWORD = prompt("Neo4j password", secret=True).strip()

if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
    _prompt_if_missing()

# 4) Final validation
if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
    raise RuntimeError(
        "Neo4j credentials not provided. Set env vars (NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD) "
        "or run bootstrap_neo4j.py once to save them, or run from a terminal to be prompted."
    )
