import json
import logging
import os
import re
from pathlib import Path

from groq import Groq
from neo4j import GraphDatabase
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("cypher_translation")
logger.setLevel(logging.INFO)
_handler = logging.FileHandler(LOG_DIR / "cypher_queries.log", encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_handler)

FEW_SHOT_EXAMPLES = [
    {
        "question": "Who argued against GCP?",
        "cypher": 'MATCH (p:Person)-[r:ARGUED_AGAINST]->(t:Technology {name:"GCP"}) RETURN p, r, t ORDER BY r.timestamp',
    },
    {
        "question": "What technology did Sarah Chen advocate for?",
        "cypher": 'MATCH (p:Person {name:"Sarah Chen"})-[r:ADVOCATED_FOR]->(t:Technology) RETURN p, r, t ORDER BY r.timestamp',
    },
    {
        "question": "Which decisions approved the migration to GCP?",
        "cypher": 'MATCH (d:Decision)-[r:APPROVED]->(t:Technology) WHERE t.name="GCP" RETURN d, r, t ORDER BY r.timestamp',
    },
]

SYSTEM_PROMPT = """You are a Cypher query generator for a temporal knowledge graph. The graph contains nodes with labels Person, Technology, and Decision, and relationships of types: ADVOCATED_FOR, ARGUED_AGAINST, COMMITTED_CODE, RAISED_CONCERN, APPROVED, REPLACED_BY.

Rules:
1. Generate ONLY a valid Cypher query. No preamble, no explanation, no markdown fences.
2. Use the exact node labels and relationship types provided in the schema below.
3. Always ORDER results by timestamp when timestamp is available.
4. Use parameterized queries where appropriate (e.g., $name for string parameters).
5. Return nodes and relationships explicitly with RETURN clause.

Live schema:
{schema}

Few-shot examples:

Question: "Who argued against GCP?"
Cypher: MATCH (p:Person)-[r:ARGUED_AGAINST]->(t:Technology {{name:"GCP"}}) RETURN p, r, t ORDER BY r.timestamp

Question: "What technology did Sarah Chen advocate for?"
Cypher: MATCH (p:Person {{name:"Sarah Chen"}})-[r:ADVOCATED_FOR]->(t:Technology) RETURN p, r, t ORDER BY r.timestamp

Question: "Which decisions approved the migration to GCP?"
Cypher: MATCH (d:Decision)-[r:APPROVED]->(t:Technology) WHERE t.name="GCP" RETURN d, r, t ORDER BY r.timestamp

Now generate a Cypher query for this question:
{question}

Cypher:""".strip()

ERROR_CORRECTION_PROMPT = """The following Cypher query failed with this error:
{error}

Failed query:
{failed_query}

Schema:
{schema}

Original question:
{question}

Fix the query and return ONLY a corrected valid Cypher query. No preamble, no explanation, no markdown fences.

Cypher:""".strip()


def _get_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment or .env file")
    return Groq(api_key=api_key)


def _get_neo4j_driver() -> GraphDatabase.driver:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j")
    return GraphDatabase.driver(uri, auth=(user, password))


def _fetch_schema(driver: GraphDatabase.driver) -> str:
    schema_parts = []
    try:
        with driver.session() as session:
            labels_result = session.run("CALL db.labels()")
            labels = [record["label"] for record in labels_result]
            schema_parts.append(f"Node labels: {', '.join(labels)}")

            rel_types_result = session.run("CALL db.relationshipTypes()")
            rel_types = [record["relationshipType"] for record in rel_types_result]
            schema_parts.append(f"Relationship types: {', '.join(rel_types)}")

            prop_keys_result = session.run("CALL db.propertyKeys()")
            prop_keys = [record["propertyKey"] for record in prop_keys_result]
            schema_parts.append(f"Property keys: {', '.join(prop_keys)}")
    except Exception as exc:
        logger.error("Failed to fetch Neo4j schema: %s", exc)
        schema_parts.append("Node labels: Person, Technology, Decision")
        schema_parts.append("Relationship types: ADVOCATED_FOR, ARGUED_AGAINST, COMMITTED_CODE, RAISED_CONCERN, APPROVED, REPLACED_BY")
        schema_parts.append("Property keys: name, type, timestamp, source_ref, confidence, source, relation, target")

    return "\n".join(schema_parts)


def _execute_cypher(driver: GraphDatabase.driver, cypher_query: str) -> dict:
    try:
        with driver.session() as session:
            result = session.run(cypher_query)
            columns = result.keys()
            records = []
            for record in result:
                record_dict = {}
                for col in columns:
                    value = record[col]
                    if hasattr(value, "labels"):
                        record_dict[col] = {"id": value.id, "labels": list(value.labels), "properties": dict(value)}
                    elif hasattr(value, "type"):
                        rel_type = value.type
                        start_props = {}
                        end_props = {}
                        try:
                            start_props = dict(value.start_node) if value.start_node else {}
                        except Exception:
                            pass
                        try:
                            end_props = dict(value.end_node) if value.end_node else {}
                        except Exception:
                            pass
                        record_dict[col] = {
                            "id": value.id,
                            "type": rel_type,
                            "start_node": value.start_node.id if value.start_node else None,
                            "end_node": value.end_node.id if value.end_node else None,
                            "start_name": start_props.get("name", str(value.start_node.id) if value.start_node else ""),
                            "end_name": end_props.get("name", str(value.end_node.id) if value.end_node else ""),
                            "properties": dict(value),
                        }
                    else:
                        record_dict[col] = str(value) if value is not None else None
                records.append(record_dict)
            return {"success": True, "records": records, "columns": columns}
    except Exception as exc:
        logger.error("Cypher execution failed: %s", exc)
        return {"success": False, "error": str(exc)}


def _parse_cypher_response(raw_response: str) -> str:
    text = raw_response.strip()
    text = re.sub(r"^```cypher\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def translate_and_query(question: str, graph_connection: GraphDatabase.driver | None = None) -> dict:
    driver = graph_connection or _get_neo4j_driver()
    schema = _fetch_schema(driver)

    client = _get_groq_client()
    prompt = SYSTEM_PROMPT.format(schema=schema, question=question)

    try:
        response = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[{"role": "system", "content": "You generate only valid Cypher queries for a temporal knowledge graph."}, {"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        )
        raw_cypher = response.choices[0].message.content
    except Exception as exc:
        logger.error("Groq API call failed in translate_and_query: %s", exc)
        return {"success": False, "reason": f"LLM call failed: {exc}"}

    cypher_query = _parse_cypher_response(raw_cypher)
    _log_llm_call("cypher_translation", prompt, raw_cypher, question)
    logger.info("Generated Cypher (attempt 1): %s", cypher_query)

    result = _execute_cypher(driver, cypher_query)

    if not result["success"] or not result.get("records"):
        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            logger.info("Cypher query failed (attempt 1): %s", error_msg)

            correction_prompt = ERROR_CORRECTION_PROMPT.format(
                error=error_msg,
                failed_query=cypher_query,
                schema=schema,
                question=question,
            )

            try:
                correction_response = client.chat.completions.create(
                    model="llama-3.1-70b-versatile",
                    messages=[{"role": "system", "content": "You fix broken Cypher queries. Return ONLY the corrected query."}, {"role": "user", "content": correction_prompt}],
                    temperature=0.0,
                    max_tokens=1024,
                )
                corrected_cypher = correction_response.choices[0].message.content
            except Exception as exc:
                logger.error("Retry LLM call failed: %s", exc)
                return {"success": False, "reason": f"Retry LLM call failed: {exc}"}

            corrected_cypher = _parse_cypher_response(corrected_cypher)
            _log_llm_call("cypher_translation_retry", correction_prompt, corrected_cypher, question)
            logger.info("Generated Cypher (attempt 2 - retry): %s", corrected_cypher)
            cypher_query = corrected_cypher

            result = _execute_cypher(driver, cypher_query)

            if not result["success"]:
                logger.error("Cypher query failed after retry: %s", result.get("error"))
                return {"success": False, "reason": f"Cypher execution failed after retry: {result.get('error')}"}

        if not result.get("records"):
            logger.info("Cypher query returned zero results for question: %s", question)
            return {"success": True, "nodes": [], "edges": [], "raw_cypher": cypher_query, "note": "Query executed successfully but returned zero results"}

    nodes = []
    edges = []
    seen_nodes = set()

    for record in result.get("records", []):
        for col, value in record.items():
            if isinstance(value, dict) and "labels" in value and col not in seen_nodes:
                node_id = value.get("id")
                props = value.get("properties", {})
                node_label = value.get("labels", ["Unknown"])[0]
                node_name = props.get("name", str(node_id))
                if node_name not in seen_nodes:
                    seen_nodes.add(node_name)
                    nodes.append(
                        {
                            "id": f"node-{node_name.lower().replace(' ', '-')}",
                            "label": node_name,
                            "type": node_label,
                            "timestamp": props.get("timestamp", ""),
                        }
                    )
            elif isinstance(value, dict) and "type" in value and "start_name" in value:
                props = value.get("properties", {})
                rel_type = value.get("type", "")
                edges.append(
                    {
                        "source": value.get("start_name", ""),
                        "target": value.get("end_name", ""),
                        "relation": rel_type,
                        "timestamp": props.get("timestamp", ""),
                        "confidence": props.get("confidence", 0.0),
                        "source_ref": props.get("source_ref", ""),
                    }
                )

    if not edges:
        for record in result.get("records", []):
            for col, value in record.items():
                if isinstance(value, dict) and "type" in value and "start_name" in value:
                    props = value.get("properties", {})
                    edges.append(
                        {
                            "source": value.get("start_name", ""),
                            "target": value.get("end_name", ""),
                            "relation": value.get("type", ""),
                            "timestamp": props.get("timestamp", ""),
                            "confidence": props.get("confidence", 0.0),
                            "source_ref": props.get("source_ref", ""),
                        }
                    )

    sorted_edges = sorted(edges, key=lambda e: e.get("timestamp", ""))

    return {
        "success": True,
        "nodes": nodes,
        "edges": sorted_edges,
        "raw_cypher": cypher_query,
    }


def _log_llm_call(module: str, prompt: str, response: str, context: str) -> None:
    log_file = LOG_DIR / "cypher_queries.log"
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write(f"--- Context: {context} ---\n")
        fh.write(f"PROMPT:\n{prompt}\n")
        fh.write(f"RESPONSE:\n{response}\n")
        fh.write(f"---\n\n")


if __name__ == "__main__":
    driver = _get_neo4j_driver()
    result = translate_and_query("Why did we switch from AWS to GCP in 2023?", driver)
    print(json.dumps(result, indent=2, default=str))
    driver.close()