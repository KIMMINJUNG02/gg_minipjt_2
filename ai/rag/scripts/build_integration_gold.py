"""develop의 7개 서비스 유물을 feature Gold schema의 artifact-unit chunk로 만든다."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PREFIXES = {"bon": "bon", "duk": "deoksu", "jub": "jeopsu", "ssu": "sinsu"}


def chunk_id(artifact_id: str) -> str:
    prefix = artifact_id[:3]
    number = artifact_id[3:]
    return f"nmm-{PREFIXES[prefix]}-{number}-00:desc-00"


def build(metadata_csv: Path) -> list[dict]:
    with metadata_csv.open(encoding="utf-8-sig", newline="") as handle:
        source = list(csv.DictReader(handle))
    rows = []
    for item in source:
        text = f"{item['artifact_name']} — {item['description'].strip()}"
        rows.append({
            "chunk_id": chunk_id(item["artifact_id"]),
            "chunk_type": "artifact",
            "parent_type": "relic",
            "parent_id": chunk_id(item["artifact_id"]).split(":", 1)[0],
            "relic_label": item["accession_no"],
            "text": text,
            "char_len": len(text),
            "metadata": {
                "record_type": "artifact",
                "collection_name": item["source"],
                "nationality": "한국",
                "period": "",
                "material_l1": "",
                "material_l2": "",
                "purpose_l1": "",
                "purpose_l2": "",
                "find_place_l1": "",
                "find_place_l2": "",
                "designations": [],
                "has_description": bool(item["description"].strip()),
                "has_image": False,
            },
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=ROOT / "data/metadata.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/gold/gold0929.jsonl")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in build(args.metadata):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(build(args.metadata))} artifact chunks to {args.output}")


if __name__ == "__main__":
    main()
