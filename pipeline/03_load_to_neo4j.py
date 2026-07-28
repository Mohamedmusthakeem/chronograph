import json
from pathlib import Path
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(ROOT := Path(__file__).resolve().parents[1] / ".env")

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "")
TRIPLES_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "triples.json"


def load_triples() -> dict:
    with TRIPLES_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    payload = load_triples()
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        with driver.session() as session:
            session.run("CREATE CONSTRAINT person_name_unique IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE")
            session.run("CREATE CONSTRAINT technology_name_unique IF NOT EXISTS FOR (t:Technology) REQUIRE t.name IS UNIQUE")
            session.run("CREATE CONSTRAINT decision_name_unique IF NOT EXISTS FOR (d:Decision) REQUIRE d.name IS UNIQUE")
            for entity in payload["entities"]:
                label = entity["type"]
                session.run(
                    f"MERGE (n:{label} {{name: $name}}) SET n.type = $type",
                    name=entity["name"],
                    type=entity["type"],
                )
            for relation in payload["relations"]:
                session.run(
                    """
                    MATCH (source {name: $source})
                    MATCH (target {name: $target})
                    MERGE (source)-[rel:RELATES_TO {relation: $relation, timestamp: $timestamp, confidence_score: $confidence, source_ref: $source_ref}]->(target)
                    SET rel.relation = $relation,
                        rel.timestamp = $timestamp,
                        rel.confidence_score = $confidence,
                        rel.source_ref = $source_ref
                    """,
                    source=relation["source"],
                    target=relation["target"],
                    relation=relation["relation"],
                    timestamp=relation["timestamp"],
                    confidence=relation["confidence"],
                    source_ref=relation["source_ref"],
                )
            counts = session.run("""
                MATCH (n)
                RETURN count(n) AS node_count
            """).single()
            edge_count = session.run("""
                MATCH ()-[r]->()
                RETURN count(r) AS edge_count
            """).single()
            print(f"Loaded graph with {counts['node_count']} nodes and {edge_count['edge_count']} edges")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
