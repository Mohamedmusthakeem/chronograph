import json
import os
import sys
from pathlib import Path

from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai.extraction import run_extraction_batch
from ai.query_translation import translate_and_query, _get_neo4j_driver
from ai.synthesis import synthesize_narrative


def load_triples_to_neo4j(driver, triples: dict) -> int:
    relations = triples.get("relations", [])
    entities = triples.get("entities", [])
    loaded = 0

    with driver.session() as session:
        for entity in entities:
            name = entity.get("name")
            etype = entity.get("type")
            if not name or not etype:
                continue
            session.run(
                "MERGE (n:`{}` {name: $name}) SET n.type = $type".format(etype),
                name=name,
                type=etype,
            )
            loaded += 1

        for relation in relations:
            source = relation.get("source")
            target = relation.get("target")
            rel_type = relation.get("relation")
            timestamp = relation.get("timestamp", "")
            confidence = relation.get("confidence", 0.0)
            source_ref = relation.get("source_ref", "")

            if not source or not target or not rel_type:
                continue

            session.run(
                "MATCH (s) WHERE s.name = $source "
                "MATCH (t) WHERE t.name = $target "
                "MERGE (s)-[r:`{}`]->(t) "
                "SET r.timestamp = $timestamp, r.confidence = $confidence, r.source_ref = $source_ref".format(
                    rel_type
                ),
                source=source,
                target=target,
                timestamp=timestamp,
                confidence=confidence,
                source_ref=source_ref,
            )
            loaded += 1

    return loaded


def main():
    print("=" * 60)
    print("ChronoGraph AI Pipeline Integration Test")
    print("=" * 60)

    print("\n--- Step 1: Run extraction on all mock files ---")
    input_files = [
        "data/raw/slack_messages.json",
        "data/raw/git_commits.json",
        "data/raw/jira_tickets.json",
    ]
    triples = run_extraction_batch(input_files)

    triples_path = ROOT / "data" / "processed" / "triples.json"
    if triples_path.exists():
        with open(triples_path, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        print(f"triples.json populated: {len(saved.get('entities', []))} entities, {len(saved.get('relations', []))} relations")
    else:
        print("ERROR: triples.json was not created", file=sys.stderr)
        return

    print("\n--- Step 2: Load 5-10 triples into Neo4j ---")
    driver = None
    try:
        driver = _get_neo4j_driver()
        driver.verify_connectivity()
        print("Neo4j connection verified")

        sample_triples = {
            "entities": triples.get("entities", [])[:10],
            "relations": triples.get("relations", [])[:10],
            "records": triples.get("records", []),
        }
        loaded_count = load_triples_to_neo4j(driver, sample_triples)
        print(f"Loaded {loaded_count} triples into Neo4j")
    except Exception as exc:
        print(f"WARNING: Neo4j connection failed ({exc}). Skipping graph loading and query steps.")
        driver = None

    print("\n--- Step 3: Translate NL question to Cypher and execute ---")
    question = "Why did we switch from AWS to GCP in 2023?"
    if driver:
        try:
            query_result = translate_and_query(question, driver)
            print(f"Query success: {query_result.get('success')}")
            print(f"Generated Cypher: {query_result.get('raw_cypher', 'N/A')}")
            print(f"Nodes returned: {len(query_result.get('nodes', []))}")
            print(f"Edges returned: {len(query_result.get('edges', []))}")
        except Exception as exc:
            print(f"Query translation failed: {exc}")
            query_result = {"success": False, "reason": str(exc)}
    else:
        print("Skipping query translation (no Neo4j connection)")
        query_result = {"success": False, "reason": "No Neo4j connection"}

    print("\n--- Step 4: Synthesize narrative from subgraph ---")
    if query_result.get("success") and query_result.get("edges"):
        subgraph = {
            "nodes": query_result.get("nodes", []),
            "edges": query_result.get("edges", []),
        }

        sources = {}
        for relation in triples.get("relations", []):
            source_ref = relation.get("source_ref", "")
            for record in triples.get("records", []):
                if record.get("id") == source_ref:
                    sources[source_ref] = {
                        "raw_text": record.get("raw_text", ""),
                        "author": record.get("author", ""),
                        "timestamp": record.get("timestamp", ""),
                    }
                    break

        try:
            narrative_result = synthesize_narrative(question, subgraph, sources)
            print(f"\n{'=' * 60}")
            print("FINAL NARRATIVE")
            print(f"{'=' * 60}")
            print(narrative_result.get("narrative", "No narrative generated."))
            print(f"\nCitations: {json.dumps(narrative_result.get('citations', {}), indent=2)}")
            print(f"Hallucination check: {narrative_result.get('hallucination_check', 'N/A')}")
        except Exception as exc:
            print(f"Synthesis failed: {exc}")
    else:
        print("Skipping synthesis (no query results or no Neo4j connection)")
        print("Attempting synthesis with sample data from extraction...")

        sample_edges = triples.get("relations", [])[:5]
        sample_nodes = []
        seen = set()
        for rel in sample_edges:
            for name in [rel.get("source", ""), rel.get("target", "")]:
                if name and name not in seen:
                    seen.add(name)
                    etype = "Technology"
                    for entity in triples.get("entities", []):
                        if entity.get("name") == name:
                            etype = entity.get("type", "Technology")
                            break
                    sample_nodes.append({"id": f"node-{name.lower().replace(' ', '-')}", "label": name, "type": etype, "timestamp": rel.get("timestamp", "")})

        subgraph = {"nodes": sample_nodes, "edges": sample_edges}
        sources = {}
        for relation in sample_edges:
            source_ref = relation.get("source_ref", "")
            for record in triples.get("records", []):
                if record.get("id") == source_ref:
                    sources[source_ref] = {
                        "raw_text": record.get("raw_text", ""),
                        "author": record.get("author", ""),
                        "timestamp": record.get("timestamp", ""),
                    }
                    break

        try:
            narrative_result = synthesize_narrative(question, subgraph, sources)
            print(f"\n{'=' * 60}")
            print("FINAL NARRATIVE (from extraction sample data)")
            print(f"{'=' * 60}")
            print(narrative_result.get("narrative", "No narrative generated."))
            print(f"\nCitations: {json.dumps(narrative_result.get('citations', {}), indent=2)}")
            print(f"Hallucination check: {narrative_result.get('hallucination_check', 'N/A')}")
        except Exception as exc:
            print(f"Synthesis failed: {exc}")

    if driver:
        driver.close()

    print("\n" + "=" * 60)
    print("Pipeline test complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()