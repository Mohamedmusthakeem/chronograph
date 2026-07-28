import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_PATH = ROOT / "data" / "processed" / "triples.json"


def load_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in [RAW_DIR / "slack_messages.json", RAW_DIR / "git_commits.json", RAW_DIR / "jira_tickets.json"]:
        with path.open("r", encoding="utf-8") as handle:
            records.extend(json.load(handle))
    return records


def build_mock_triples(records: list[dict[str, Any]]) -> dict[str, Any]:
    entities: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    seen_entities: set[tuple[str, str]] = set()

    person_names = {"Sarah Chen", "Mina Patel", "Omar Ruiz", "Nadia Brooks", "Leo Kim"}
    for name in person_names:
        if (name, "Person") not in seen_entities:
            entities.append({"name": name, "type": "Person"})
            seen_entities.add((name, "Person"))

    technologies = ["AWS", "GCP", "Kubernetes", "IAM", "Pub/Sub"]
    for name in technologies:
        if (name, "Technology") not in seen_entities:
            entities.append({"name": name, "type": "Technology"})
            seen_entities.add((name, "Technology"))

    decisions = ["Move to GCP", "Staged migration"]
    for name in decisions:
        if (name, "Decision") not in seen_entities:
            entities.append({"name": name, "type": "Decision"})
            seen_entities.add((name, "Decision"))

    relation_templates = [
        ("Sarah Chen", "ADVOCATED_FOR", "GCP", "2023-01-12T09:00:00Z", 0.95, "slack-001"),
        ("Mina Patel", "APPROVED", "Move to GCP", "2023-05-12T09:05:00Z", 0.92, "slack-007"),
        ("Omar Ruiz", "COMMITTED_CODE", "GCP", "2023-03-18T12:30:00Z", 0.9, "git-001"),
        ("Sarah Chen", "RAISED_CONCERN", "IAM", "2023-04-02T08:45:00Z", 0.88, "slack-005"),
        ("AWS", "REPLACED_BY", "GCP", "2023-08-03T09:20:00Z", 0.94, "jira-001"),
        ("Kubernetes", "COMMITTED_CODE", "GCP", "2023-04-19T08:50:00Z", 0.86, "git-002"),
    ]

    for source, relation, target, timestamp, confidence, ref in relation_templates:
        relations.append({
            "source": source,
            "relation": relation,
            "target": target,
            "timestamp": timestamp,
            "confidence": confidence,
            "source_ref": ref,
        })

    return {"entities": entities, "relations": relations, "records": records}


def main() -> None:
    records = load_records()
    payload = build_mock_triples(records)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(f"Extracted {len(payload['entities'])} entities and {len(payload['relations'])} relations to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
