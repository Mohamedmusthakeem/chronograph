import json
import logging
import os
import re
from pathlib import Path

from groq import Groq
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("synthesis")
logger.setLevel(logging.INFO)
_handler = logging.FileHandler(LOG_DIR / "hallucination_checks.log", encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_handler)

SYNTHESIS_PROMPT = """You are a narrative synthesis engine for a temporal evidence graph. Given a chronologically-sorted subgraph and source materials, write a narrative answer.

Rules:
1. Write in plain English, 2-4 paragraphs.
2. Present events and opinions in chronological order.
3. ONLY state facts present in the provided subgraph. Do NOT add outside knowledge or infer beyond what is given.
4. Insert a citation marker like [1], [2], [3] after every specific claim, mapping to the source_ref of the edge or node that supports it.
5. The citations dict maps citation numbers to source_ref values. Use this mapping to place markers correctly.

Subgraph nodes:
{nodes_json}

Subgraph edges (chronologically sorted):
{edges_json}

Question: {question}

Write the narrative answer now:""".strip()

HALLUCINATION_PROMPT = """You are a hallucination detector. Given a narrative and the original subgraph data, check if the narrative contains any claim NOT supported by the provided subgraph.

Narrative:
{narrative}

Subgraph edges:
{edges_json}

Subgraph nodes:
{nodes_json}

Answer yes or no, then explain briefly.
Does this narrative contain any claim NOT supported by the provided subgraph? Answer:""".strip()


def _get_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment or .env file")
    return Groq(api_key=api_key)


def _build_citation_map(subgraph: dict, sources: dict) -> dict:
    citation_map = {}
    edges = subgraph.get("edges", [])
    nodes = subgraph.get("nodes", [])
    claim_index = 1

    for edge in edges:
        source_ref = edge.get("source_ref", "")
        if source_ref and source_ref not in citation_map.values():
            citation_map[str(claim_index)] = source_ref
            claim_index += 1

    for node in nodes:
        node_id = node.get("id", "")
        if node_id and node_id not in citation_map.values():
            citation_map[str(claim_index)] = node_id
            claim_index += 1

    return citation_map


def _parse_citations(narrative: str, citation_map: dict) -> dict:
    citations = {}
    for marker, source_ref in citation_map.items():
        pattern = re.escape(f"[{marker}]")
        if re.search(pattern, narrative):
            citations[marker] = source_ref
    return citations


def synthesize_narrative(question: str, subgraph: dict, sources: dict) -> dict:
    nodes = subgraph.get("nodes", [])
    edges = subgraph.get("edges", [])

    nodes_json = json.dumps(nodes, indent=2, default=str)
    edges_json = json.dumps(edges, indent=2, default=str)

    client = _get_groq_client()
    prompt = SYNTHESIS_PROMPT.format(
        nodes_json=nodes_json,
        edges_json=edges_json,
        question=question,
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[{"role": "system", "content": "You write factual narratives from graph evidence. Only state what is in the subgraph."}, {"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=2048,
        )
        narrative = response.choices[0].message.content
    except Exception as exc:
        raise RuntimeError(f"Groq API call failed in synthesize_narrative: {exc}") from exc

    _log_llm_call("synthesis", prompt, narrative, question)

    citation_map = _build_citation_map(subgraph, sources)
    citations = _parse_citations(narrative, citation_map)

    hallucination_prompt = HALLUCINATION_PROMPT.format(
        narrative=narrative,
        edges_json=edges_json,
        nodes_json=nodes_json,
    )

    try:
        hallucination_response = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[{"role": "system", "content": "You check narratives for unsupported claims. Answer only yes or no, then explain."}, {"role": "user", "content": hallucination_prompt}],
            temperature=0.0,
            max_tokens=512,
        )
        hallucination_result = hallucination_response.choices[0].message.content
    except Exception as exc:
        hallucination_result = f"Hallucination check failed: {exc}"

    _log_llm_call("hallucination_check", hallucination_prompt, hallucination_result, question)
    logger.info("Hallucination check result for question '%s': %s", question, hallucination_result)

    return {
        "narrative": narrative,
        "citations": citations,
        "hallucination_check": hallucination_result,
    }


def _log_llm_call(module: str, prompt: str, response: str, context: str) -> None:
    log_file = LOG_DIR / "synthesis_llm_calls.log"
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write(f"--- Context: {context} ---\n")
        fh.write(f"PROMPT:\n{prompt}\n")
        fh.write(f"RESPONSE:\n{response}\n")
        fh.write(f"---\n\n")


if __name__ == "__main__":
    sample_subgraph = {
        "nodes": [
            {"id": "node-sarah-chen", "label": "Sarah Chen", "type": "Person", "timestamp": "2023-01-12T09:00:00Z"},
            {"id": "node-gcp", "label": "GCP", "type": "Technology", "timestamp": "2023-01-12T09:00:00Z"},
        ],
        "edges": [
            {"source": "Sarah Chen", "target": "GCP", "relation": "ADVOCATED_FOR", "timestamp": "2023-01-12T09:00:00Z", "confidence": 0.95, "source_ref": "slack-001"},
        ],
    }
    sample_sources = {
        "slack-001": {"raw_text": "The AWS networking layer is causing regional failover issues and I think the GCP managed networking story is more resilient.", "author": "Sarah Chen", "timestamp": "2023-01-12T09:00:00Z"},
    }
    result = synthesize_narrative("Why did we switch from AWS to GCP?", sample_subgraph, sample_sources)
    print(json.dumps(result, indent=2, default=str))