import json
import logging
import os
import re
import socket
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, filename=ROOT / "logs" / "backend.log", format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("chronograph")

app = FastAPI(title="ChronoGraph API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str
    history: list[dict[str, str]] | None = None


class QueryResponse(BaseModel):
    question: str
    narrative: str
    citations: list[dict[str, str]]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    sources: list[dict[str, Any]]


def load_triples() -> dict[str, Any]:
    path = ROOT / "data" / "processed" / "triples.json"
    if not path.exists():
        return {"entities": [], "relations": [], "records": []}

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _infer_entity_type(name: str) -> str:
    if name in {"Sarah Chen", "Mina Patel", "Omar Ruiz", "Nadia Brooks", "Leo Kim"}:
        return "Person"
    if name in {"AWS", "GCP", "Kubernetes", "IAM", "Pub/Sub"}:
        return "Technology"
    if name in {"Move to GCP", "Staged migration"}:
        return "Decision"
    return "Technology"


def get_available_port(start_port: int) -> int:
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
            except OSError:
                port += 1
                continue
            return port


def resolve_follow_up(question: str, history: list[dict[str, str]] | None) -> str:
    if not history:
        return question

    lowered = question.lower()
    if not any(token in lowered for token in ["it", "that", "this", "they", "them"]):
        return question

    previous_user = next(
        (item.get("content", "") for item in reversed(history) if item.get("role") == "user"),
        "",
    )
    if not previous_user:
        return question

    previous_user_lower = previous_user.lower()
    if "aws to gcp" in previous_user_lower or "gcp" in previous_user_lower:
        topic = "the AWS to GCP migration"
    elif "concern" in previous_user_lower:
        topic = "the migration concerns"
    else:
        topic = "the migration story"

    return question.replace("it", topic).replace("that", topic).replace("this", topic)


def build_graph_response(question: str, history: list[dict[str, str]] | None) -> dict[str, Any]:
    resolved_question = resolve_follow_up(question, history)
    lowered = resolved_question.lower()
    payload = load_triples()
    relations = payload.get("relations", [])
    entities = payload.get("entities", [])
    records = payload.get("records", [])
    records_by_id = {record.get("id"): record for record in records if isinstance(record, dict) and record.get("id")}

    entity_types = {entity.get("name"): entity.get("type") for entity in entities if isinstance(entity, dict) and entity.get("name")}

    if "sarah" in lowered and ("what did" in lowered or "say" in lowered or "about" in lowered):
        matched_relations = [
            relation
            for relation in relations
            if relation.get("source") == "Sarah Chen" or relation.get("target") == "Sarah Chen"
        ]
    elif "concern" in lowered:
        matched_relations = [
            relation
            for relation in relations
            if relation.get("relation") == "RAISED_CONCERN" or relation.get("target") == "IAM"
        ]
    else:
        matched_relations = sorted(relations, key=lambda item: item.get("confidence", 0), reverse=True)[:4]

    if not matched_relations:
        matched_relations = sorted(relations, key=lambda item: item.get("confidence", 0), reverse=True)[:3]

    nodes: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    for relation in matched_relations:
        for name in [relation.get("source"), relation.get("target")]:
            if not name or name in seen_nodes:
                continue
            node_type = entity_types.get(name, _infer_entity_type(name))
            nodes.append({
                "id": f"node-{_slugify(name)}",
                "label": name,
                "type": node_type,
                "timestamp": relation.get("timestamp", "2023-01-01T00:00:00Z"),
                "position": {
                    "x": len(nodes) * 220,
                    "y": 80 if node_type == "Person" else 220 if node_type == "Technology" else 360,
                },
            })
            seen_nodes.add(name)

    edges = []
    citations = []
    sources = []
    narrative_parts = []

    for index, relation in enumerate(matched_relations, start=1):
        edge_id = f"edge-{index}"
        source_id = relation.get("source_ref") or f"source-{index}"
        edge = {
            "id": edge_id,
            "source": f"node-{_slugify(relation.get('source', 'unknown'))}",
            "target": f"node-{_slugify(relation.get('target', 'unknown'))}",
            "relation": relation.get("relation", "RELATED_TO"),
            "timestamp": relation.get("timestamp", "2023-01-01T00:00:00Z"),
            "source_ref": source_id,
        }
        edges.append(edge)
        citations.append({"marker": f"[{index}]", "source_id": source_id, "target_id": edge_id})

        record = records_by_id.get(source_id, {})
        if record:
            sources.append({
                "source_id": source_id,
                "raw_text": record.get("raw_text", "Evidence from the processed graph."),
                "author": record.get("author", "Unknown"),
                "timestamp": record.get("timestamp", relation.get("timestamp", "2023-01-01T00:00:00Z")),
                "source_type": record.get("source_type", "unknown"),
            })

        if relation.get("relation") == "ADVOCATED_FOR":
            narrative_parts.append(
                f"[{index}] {relation.get('source')} advocated for {relation.get('target')} and the evidence points to a stronger platform story around that choice."
            )
        elif relation.get("relation") == "RAISED_CONCERN":
            narrative_parts.append(
                f"[{index}] {relation.get('source')} raised a concern about {relation.get('target')} and flagged readiness risk before the rollout continued."
            )
        else:
            narrative_parts.append(
                f"[{index}] The graph shows a {relation.get('relation', 'related')} link between {relation.get('source')} and {relation.get('target')} during the migration timeline."
            )

    if not narrative_parts:
        narrative_parts.append("[1] The processed evidence graph contains a relevant signal for the migration story.")

    return {
        "narrative": " ".join(narrative_parts),
        "citations": citations,
        "nodes": nodes,
        "edges": edges,
        "sources": sources,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/smoke")
def smoke() -> dict[str, Any]:
    return {
        "status": "ok",
        "records": len(load_triples().get("records", [])),
        "relations": len(load_triples().get("relations", [])),
    }


@app.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest) -> QueryResponse:
    try:
        resolved_question = resolve_follow_up(payload.question, payload.history)
        logger.info("Received question: %s | resolved: %s", payload.question, resolved_question)
        graph_payload = build_graph_response(payload.question, payload.history)

        response = QueryResponse(
            question=payload.question,
            narrative=graph_payload["narrative"],
            citations=graph_payload["citations"],
            nodes=graph_payload["nodes"],
            edges=graph_payload["edges"],
            sources=graph_payload["sources"],
        )
        logger.info("Returning response for question: %s", payload.question)
        return response
    except Exception as exc:  # pragma: no cover
        logger.exception("Query failed: %s", exc)
        raise HTTPException(status_code=500, detail="The backend could not process the query") from exc


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    resolved_port = get_available_port(port)
    logger.info("Starting backend on port %s", resolved_port)
    uvicorn.run(app, host="0.0.0.0", port=resolved_port)
