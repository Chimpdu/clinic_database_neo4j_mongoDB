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

def insert_user(name: str, password: str):
    with _driver.session() as s:
        s.run(
            "MERGE (u:User {name:$n}) "
            "ON CREATE SET u.password=$p "
            "ON MATCH SET u.password=u.password",
            n=name, p=password
        )
