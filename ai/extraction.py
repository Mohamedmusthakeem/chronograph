import json
import logging
import os
import sys
from pathlib import Path

from groq import Groq
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("extraction")
logger.setLevel(logging.INFO)
_handler = logging.FileHandler(LOG_DIR / "extraction_rejections.log", encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_handler)

ALLOWED_ENTITY_TYPES = {"Person", "Technology", "Decision"}
ALLOWED_RELATION_TYPES = {
    "ADVOCATED_FOR",
    "ARGUED_AGAINST",
    "COMMITTED_CODE",
    "RAISED_CONCERN",
    "APPROVED",
    "REPLACED_BY",
}

EXTRACTION_PROMPT = """You are a temporal graph extraction engine. Given a raw text record from Slack, Git, or Jira, extract entities and relationships as graph triples.

Entity types allowed: Person, Technology, Decision
Relation types allowed: ADVOCATED_FOR, ARGUED_AGAINST, COMMITTED_CODE, RAISED_CONCERN, APPROVED, REPLACED_BY

IMPORTANT RULES:
1. ONLY extract relationships you are confident are directly stated in the text. Do NOT infer relationships that are not explicitly expressed.
2. Every relation must include a self-reported confidence score between 0.0 and 1.0.
3. Output MUST be strict JSON only — no preamble, no markdown fences, no explanatory text.
4. Inherit the timestamp from the record and use the record's id as source_ref.

Few-shot examples:

Example 1:
Input record: {{"id": "slack-001", "source_type": "slack", "author": "Sarah Chen", "timestamp": "2023-01-12T09:00:00Z", "raw_text": "The AWS networking layer is causing regional failover issues and I think the GCP managed networking story is more resilient.", "channel": "engineering"}}
Output: {{"entities": [{{"name": "Sarah Chen", "type": "Person"}}, {{"name": "AWS", "type": "Technology"}}, {{"name": "GCP", "type": "Technology"}}], "relations": [{{"source": "Sarah Chen", "relation": "ARGUED_AGAINST", "target": "AWS", "timestamp": "2023-01-12T09:00:00Z", "confidence": 0.9, "source_ref": "slack-001"}}, {{"source": "Sarah Chen", "relation": "ADVOCATED_FOR", "target": "GCP", "timestamp": "2023-01-12T09:00:00Z", "confidence": 0.95, "source_ref": "slack-001"}}]}}

Example 2:
Input record: {{"id": "jira-001", "source_type": "jira", "author": "DevOps Team", "timestamp": "2023-03-21T11:00:00Z", "raw_text": "JIRA-884: Standardize the platform on GCP and retire the AWS-only deployment path by Q4.", "project": "platform-migration"}}
Output: {{"entities": [{{"name": "GCP", "type": "Technology"}}, {{"name": "AWS", "type": "Technology"}}, {{"name": "Standardize on GCP", "type": "Decision"}}], "relations": [{{"source": "AWS", "relation": "REPLACED_BY", "target": "GCP", "timestamp": "2023-03-21T11:00:00Z", "confidence": 0.9, "source_ref": "jira-001"}}, {{"source": "DevOps Team", "relation": "APPROVED", "target": "Standardize on GCP", "timestamp": "2023-03-21T11:00:00Z", "confidence": 0.85, "source_ref": "jira-001"}}]}}

Example 3:
Input record: {{"id": "git-003", "source_type": "git", "author": "Omar Ruiz", "timestamp": "2023-05-24T10:25:00Z", "raw_text": "commit 1ba04bb: replace AWS-specific IAM assumptions with portable workload identity settings.", "repo": "platform-services"}}
Output: {{"entities": [{{"name": "Omar Ruiz", "type": "Person"}}, {{"name": "AWS", "type": "Technology"}}, {{"name": "IAM", "type": "Technology"}}], "relations": [{{"source": "Omar Ruiz", "relation": "COMMITTED_CODE", "target": "IAM", "timestamp": "2023-05-24T10:25:00Z", "confidence": 0.88, "source_ref": "git-003"}}, {{"source": "AWS", "relation": "REPLACED_BY", "target": "IAM", "timestamp": "2023-05-24T10:25:00Z", "confidence": 0.7, "source_ref": "git-003"}}]}}

Now extract from this record:
{record_json}

Output ONLY valid JSON matching the schema: {{"entities": [...], "relations": [...]}}""".strip()

FALLBACK_PROMPT = """The previous extraction produced invalid JSON. Retry with this record and return ONLY valid JSON. No preamble, no markdown fences, no explanatory text. Record: {record_json}""".strip()


def _get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment or .env file")
    return Groq(api_key=api_key)


def extract_triples(record: dict) -> dict:
    client = _get_client()
    record_json = json.dumps(record, ensure_ascii=False)
    prompt = EXTRACTION_PROMPT.format(record_json=record_json)

    try:
        response = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[{"role": "system", "content": "You are a temporal graph extraction engine that outputs only strict JSON."}, {"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=2048,
        )
        raw_output = response.choices[0].message.content
    except Exception as exc:
        raise RuntimeError(f"Groq API call failed in extract_triples for record {record.get('id', 'unknown')}: {exc}") from exc

    _log_llm_call("extraction", prompt, raw_output, record.get("id", "unknown"))

    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse Groq response as JSON for record {record.get('id', 'unknown')}: {exc}") from exc

    return result


def validate_extraction(result: dict, record: dict) -> dict:
    record_id = record.get("id", "unknown")
    rejections = []

    if not isinstance(result, dict):
        logger.info("Record %s rejected: result is not a dict, got %s", record_id, type(result).__name__)
        return {"entities": [], "relations": [], "rejected": True, "reason": "result is not a dict"}

    entities = result.get("entities", [])
    relations = result.get("relations", [])

    if not isinstance(entities, list):
        rejections.append("entities is not a list")
        entities = []
    if not isinstance(relations, list):
        rejections.append("relations is not a list")
        relations = []

    filtered_entities = []
    for entity in entities:
        if not isinstance(entity, dict):
            rejections.append(f"Skipping non-dict entity: {entity}")
            continue
        name = entity.get("name")
        etype = entity.get("type")
        if not name or not etype:
            rejections.append(f"Entity missing name or type: {entity}")
            continue
        if etype not in ALLOWED_ENTITY_TYPES:
            rejections.append(f"Entity type '{etype}' not allowed for entity '{name}'")
            continue
        filtered_entities.append({"name": name, "type": etype})

    filtered_relations = []
    for relation in relations:
        if not isinstance(relation, dict):
            rejections.append(f"Skipping non-dict relation: {relation}")
            continue
        source = relation.get("source")
        rel_type = relation.get("relation")
        target = relation.get("target")
        confidence = relation.get("confidence")

        missing = []
        if not source:
            missing.append("source")
        if not rel_type:
            missing.append("relation")
        if not target:
            missing.append("target")
        if missing:
            rejections.append(f"Relation missing fields {missing}: {relation}")
            continue

        if rel_type not in ALLOWED_RELATION_TYPES:
            rejections.append(f"Relation type '{rel_type}' not allowed for relation {source} -> {target}")
            continue

        if not isinstance(confidence, (int, float)):
            rejections.append(f"Relation confidence is not a number: {relation}")
            continue

        if confidence < 0.6:
            rejections.append(f"Relation confidence {confidence} below threshold 0.6 for {source} -> {target}")
            continue

        filtered_relations.append(
            {
                "source": source,
                "relation": rel_type,
                "target": target,
                "timestamp": record.get("timestamp", ""),
                "confidence": float(confidence),
                "source_ref": record_id,
            }
        )

    for reason in rejections:
        logger.info("Record %s rejection: %s", record_id, reason)

    return {"entities": filtered_entities, "relations": filtered_relations, "rejected": len(rejections) > 0, "rejection_reasons": rejections}


def _retry_extraction(record: dict) -> dict | None:
    client = _get_client()
    record_json = json.dumps(record, ensure_ascii=False)
    prompt = FALLBACK_PROMPT.format(record_json=record_json)

    try:
        response = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[{"role": "system", "content": "You are a strict JSON extraction engine. Return ONLY valid JSON."}, {"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=2048,
        )
        raw_output = response.choices[0].message.content
    except Exception as exc:
        logger.error("Retry extraction failed for record %s: %s", record.get("id", "unknown"), exc)
        return None

    _log_llm_call("extraction_retry", prompt, raw_output, record.get("id", "unknown"))

    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        logger.error("Retry extraction still produced invalid JSON for record %s: %s", record.get("id", "unknown"), exc)
        return None

    return result


def _log_llm_call(module: str, prompt: str, response: str, record_id: str) -> None:
    log_dir = LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{module}_llm_calls.log"
    with open(log_file, "a", encoding="utf-8") as fh:
        fh.write(f"--- Record: {record_id} ---\n")
        fh.write(f"PROMPT:\n{prompt}\n")
        fh.write(f"RESPONSE:\n{response}\n")
        fh.write(f"---\n\n")


def run_extraction_batch(input_files: list) -> list:
    total_records = 0
    total_accepted = 0
    total_rejected = 0
    rejection_reasons: dict[str, int] = {}
    all_entities = []
    all_relations = []
    all_records = []

    for input_file in input_files:
        file_path = ROOT / input_file
        if not file_path.exists():
            logger.error("Input file not found: %s", file_path)
            print(f"WARNING: Input file not found: {file_path}", file=sys.stderr)
            continue

        with open(file_path, "r", encoding="utf-8") as fh:
            records = json.load(fh)

        if not isinstance(records, list):
            logger.error("Input file %s does not contain a JSON array", file_path)
            continue

        for record in records:
            total_records += 1
            record_id = record.get("id", "unknown")

            try:
                raw_result = extract_triples(record)
            except Exception as exc:
                logger.error("Extraction failed for record %s: %s", record_id, exc)
                retry_result = _retry_extraction(record)
                if retry_result is not None:
                    try:
                        raw_result = retry_result
                    except Exception:
                        total_rejected += 1
                        rejection_reasons[str(exc)] = rejection_reasons.get(str(exc), 0) + 1
                        continue
                else:
                    total_rejected += 1
                    rejection_reasons[str(exc)] = rejection_reasons.get(str(exc), 0) + 1
                    continue

            validated = validate_extraction(raw_result, record)

            if validated.get("rejected") and not validated.get("entities") and not validated.get("relations"):
                retry_result = _retry_extraction(record)
                if retry_result is not None:
                    validated = validate_extraction(retry_result, record)

            if validated.get("entities") or validated.get("relations"):
                total_accepted += 1
            else:
                total_rejected += 1
                for reason in validated.get("rejection_reasons", []):
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

            all_entities.extend(validated.get("entities", []))
            all_relations.extend(validated.get("relations", []))
            all_records.append(record)

    output = {"entities": all_entities, "relations": all_relations, "records": all_records}
    output_path = ROOT / "data" / "processed" / "triples.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    print(f"=== Extraction Summary ===")
    print(f"Total records processed: {total_records}")
    print(f"Total triples accepted: {total_accepted}")
    print(f"Total rejected: {total_rejected}")
    print(f"Top 3 rejection reasons:")
    for reason, count in sorted(rejection_reasons.items(), key=lambda item: item[1], reverse=True)[:3]:
        print(f"  - {reason}: {count}")

    return output


if __name__ == "__main__":
    input_files = [
        "data/raw/slack_messages.json",
        "data/raw/git_commits.json",
        "data/raw/jira_tickets.json",
    ]
    run_extraction_batch(input_files)