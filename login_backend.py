# login_backend.py
from neo4j import GraphDatabase, basic_auth
from db_config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

_driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))

def check_admin(name, password) -> bool:
    with _driver.session() as s:
        rec = s.run(
            "MATCH (a:Admin {name:$n, password:$p}) RETURN 1 AS ok LIMIT 1",
            n=name, p=password
        ).single()
        return rec is not None

def check_user(name, password) -> bool:
    with _driver.session() as s:
        rec = s.run(
            "MATCH (u:User {name:$n, password:$p}) RETURN 1 AS ok LIMIT 1",
            n=name, p=password
        ).single()
        return rec is not None

def insert_user(name: str, password: str, *, person_id: str | None = None, as_admin: bool = False):
    """
    Creates login node if it doesn't exist yet.
    - If as_admin=True: create Admin node (doctors)
    - else: create User node (patients)
    Also sets a 'person_id' property used to map to Doctor/Patient even if 'name' changes.
    """
    label = "Admin" if as_admin else "User"
    with _driver.session() as s:
        s.run(
            f"MERGE (x:{label} {{name:$n}}) "
            f"ON CREATE SET x.password=$p, x.person_id=$pid "
            f"ON MATCH SET x.password=x.password",
            n=name, p=password, pid=(person_id or name)
        )

# -----helpers for account management / identity mapping -----

def get_account_person_id(name: str) -> str | None:
    with _driver.session() as s:
        rec = s.run(
            "MATCH (x) WHERE (x:Admin OR x:User) AND x.name=$n RETURN x.person_id AS pid LIMIT 1",
            n=name
        ).single()
        if rec and rec["pid"]:
            return str(rec["pid"])
        return None

def is_doctor_person(person_id: str) -> bool:
    with _driver.session() as s:
        rec = s.run("MATCH (d:Doctor {doctor_ID:$id}) RETURN 1 AS ok LIMIT 1", id=person_id).single()
        return rec is not None

def is_patient_person(person_id: str) -> bool:
    with _driver.session() as s:
        rec = s.run("MATCH (p:Patient {patient_ID:$id}) RETURN 1 AS ok LIMIT 1", id=person_id).single()
        return rec is not None

def change_own_credentials(old_name: str, *, role: str,
                           new_name: str | None = None,
                           new_password: str | None = None):
    """
    Allows the logged-in user to change their username/password.
    Preserves 'person_id' so doctor/patient linkage survives a username change.
    """
    if not new_name and not new_password:
        return
    label = "Admin" if role == "super" else "User"
    sets = []
    params = {"old": old_name}
    if new_name:
        sets.append("x.name=$new"); params["new"] = new_name
    if new_password:
        sets.append("x.password=$pwd"); params["pwd"] = new_password
    with _driver.session() as s:
        s.run(f"""
            MATCH (x:{label} {{name:$old}})
            SET {", ".join(sets)}
        """, **params)
