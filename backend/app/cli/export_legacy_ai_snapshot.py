"""Export the supplied legacy FlipBelt HTML snapshot into import-ready JSON.

The HTML is parsed as data through the same allowlisted parser used by the API.
No embedded JavaScript is executed and sensitive payment fields are removed.
"""

import hashlib
import json
import sys
from pathlib import Path

from app.api.v1.workspace import parse_import_content


def export_snapshot(source_path: Path, output_path: Path) -> None:
    source_kind, rows = parse_import_content(source_path.name, source_path.read_bytes())
    if source_kind != "html":
        raise ValueError("source must be an HTML snapshot")

    collections: dict[str, list[dict]] = {}
    for row in rows:
        source_identifier = str(row.get("__legacy_source_identifier") or "")
        collection = source_identifier.split(":", 1)[0]
        if not collection:
            continue
        collections.setdefault(collection, []).append(
            {key: value for key, value in row.items() if not str(key).startswith("__legacy_")}
        )
    payload = {
        "_migration_metadata": {
            "source_file": source_path.name,
            "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "record_count": sum(len(items) for items in collections.values()),
            "format": "flipbelt_v3_data_compatible",
        },
        **collections,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    source_path = next(project_root.glob("*v4(1).html"), None)
    if source_path is None:
        raise FileNotFoundError("legacy FlipBelt HTML snapshot was not found")
    output_path = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else project_root / "docs" / "fixtures" / "flipbelt_ai_snapshot_import.json"
    )
    export_snapshot(source_path, output_path)
    print(output_path)


if __name__ == "__main__":
    main()
