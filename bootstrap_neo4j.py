import os
import json
from pathlib import Path
from getpass import getpass
from neo4j import GraphDatabase, basic_auth

def _env_or_prompt(var, prompt, default=None, secret=False):
    val = os.getenv(var)
    if val is not None and val != "":
        return val
    msg = f"{prompt}" + (f" [{default}]" if default else "") + ": "
    if secret:
        val = getpass(msg)
    else:
        val = input(msg).strip()
    return (val or default)

def _config_path() -> Path:
    # Save alongside this script, in ./neo4j_app/credentials.json
    base = Path(__file__).resolve().parent
    d = base / "neo4j_app"
    d.mkdir(parents=True, exist_ok=True)
    return d / "credentials.json"

def main():
    uri  = (_env_or_prompt("NEO4J_URI",  "Neo4j URI (bolt/neo4j/neo4j+s)", "bolt://localhost:7687") or "").strip()
    user = (_env_or_prompt("NEO4J_USER", "Neo4j user", "neo4j") or "").strip()
    pwd  = _env_or_prompt("NEO4J_PASSWORD", "Neo4j password", None, secret=True)
    if pwd is None or str(pwd).strip() == "":
        raise RuntimeError("Neo4j password is required (no default). Set NEO4J_PASSWORD or enter it when prompted.")
    pwd = str(pwd).strip()

    driver = GraphDatabase.driver(uri, auth=basic_auth(user, pwd))
    with driver.session() as s:
        s.run("RETURN 1").single()

        # Constraints
        s.run("CREATE CONSTRAINT clinic_id   IF NOT EXISTS FOR (c:Clinic)      REQUIRE c.cli_id IS UNIQUE")
        s.run("CREATE CONSTRAINT dept_id     IF NOT EXISTS FOR (d:Department)  REQUIRE d.dept_id IS UNIQUE")
        s.run("CREATE CONSTRAINT doctor_id   IF NOT EXISTS FOR (d:Doctor)      REQUIRE d.doctor_ID IS UNIQUE")
        s.run("CREATE CONSTRAINT patient_id  IF NOT EXISTS FOR (p:Patient)     REQUIRE p.patient_ID IS UNIQUE")
        s.run("CREATE CONSTRAINT appt_id     IF NOT EXISTS FOR (a:Appointment) REQUIRE a.appoint_id IS UNIQUE")
        s.run("CREATE CONSTRAINT obser_id    IF NOT EXISTS FOR (o:Observation) REQUIRE o.obser_id IS UNIQUE")
        s.run("CREATE CONSTRAINT diagn_id    IF NOT EXISTS FOR (d:Diagnosis)   REQUIRE d.diagn_id IS UNIQUE")
        s.run("CREATE CONSTRAINT blob_oid    IF NOT EXISTS FOR (b:Blob)        REQUIRE b.oid IS UNIQUE")
        s.run("CREATE CONSTRAINT admin_name  IF NOT EXISTS FOR (a:Admin)       REQUIRE a.name IS UNIQUE")
        s.run("CREATE CONSTRAINT user_name   IF NOT EXISTS FOR (u:User)        REQUIRE u.name IS UNIQUE")

        # Seed
        s.run("""
            MERGE (a:Admin {name:'admin'})
            ON CREATE SET a.password='admin'
        """)
        s.run("""
            MERGE (u:User {name:'user1'})
            ON CREATE SET u.password='user123'
        """)
        s.run("""
            MERGE (c:Counters {id:'global'})
            ON CREATE SET c.lo_oid = 0
        """)

    driver.close()
    print("   Neo4j schema ready.")
    print("   Default admin: admin / admin")
    print("   Default normal user: user1 / user123")

    
    try:
        p = _config_path()
        data = {"uri": uri, "user": user, "password": pwd}
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        if os.name != "nt":
            os.chmod(p, 0o600)
        print(f"   Saved credentials to: {p}")
        print("   (Add this path to your .gitignore. File is per-user and not checked into source.)")
    except Exception as e:
        print(f"   Warning: could not save credentials file ({e}). You can still use env vars.")

if __name__ == "__main__":
    main()
