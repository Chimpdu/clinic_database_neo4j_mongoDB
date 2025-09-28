from contextlib import contextmanager
from neo4j import GraphDatabase, basic_auth
from db_config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

_driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))
_CURRENT_ROLE = "normal"

def set_dsn(role: str):
    global _CURRENT_ROLE
    _CURRENT_ROLE = "super" if role == "super" else "normal"

def is_admin() -> bool:
    return _CURRENT_ROLE == "super"

def require_admin():
    if not is_admin():
        raise PermissionError("Write operation not allowed for normal users.")

@contextmanager
def get_conn():
    with _driver.session() as session:
        yield session

def close_driver():
    _driver.close()
