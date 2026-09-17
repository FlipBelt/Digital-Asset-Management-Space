"""Audit and safely backfill governed-asset identifiers and code sequences.

The default mode is read-only and prints a JSON report. Use --apply only after
the database backup has completed. Existing asset names and codes are never
rewritten: the command only adds missing identifier rows and advances sequence
counters so future codes cannot collide with legacy codes.
"""

import argparse
import json
import re
from collections import defaultdict

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Asset, AssetCodeSequence, AssetIdentifier, AssetType, SourceImportRecord
from app.services.assets import ensure_internal_identifier


def build_report(apply: bool) -> dict[str, int | bool]:
    with SessionLocal() as db:
        assets = list(db.scalars(select(Asset).where(Asset.archived_at.is_(None))))
        types = {item.id: item for item in db.scalars(select(AssetType))}
        identifiers = list(
            db.scalars(
                select(AssetIdentifier).where(AssetIdentifier.archived_at.is_(None))
            )
        )
        internal_asset_ids = {
            item.asset_id
            for item in identifiers
            if item.namespace.startswith("internal:") and item.identifier_type == "asset_code"
        }
        maximums: dict[tuple[object, object], int] = defaultdict(int)
        pattern = re.compile(r"^([A-Z][A-Z0-9_]*)-(\d+)$")
        for asset in assets:
            match = pattern.match(asset.asset_code or "")
            asset_type = types.get(asset.asset_type_id)
            if match and asset_type and match.group(1) == asset_type.code_prefix:
                maximums[(asset.legal_entity_id, asset.asset_type_id)] = max(
                    maximums[(asset.legal_entity_id, asset.asset_type_id)], int(match.group(2))
                )
        records = list(
            db.scalars(
                select(SourceImportRecord).where(
                    SourceImportRecord.canonical_asset_id.is_not(None),
                    SourceImportRecord.archived_at.is_(None),
                )
            )
        )
        legacy_existing = {
            (item.source_import_record_id, item.identifier_value)
            for item in identifiers
            if item.source_import_record_id is not None
        }
        missing_internal = [item for item in assets if item.id not in internal_asset_ids]
        missing_legacy = [
            item for item in records
            if item.source_identifier and (item.id, item.source_identifier) not in legacy_existing
        ]
        report: dict[str, int | bool] = {
            "apply": apply,
            "active_assets": len(assets),
            "missing_internal_identifiers": len(missing_internal),
            "legacy_records_with_missing_identifier": len(missing_legacy),
            "sequence_rows_to_sync": len(maximums),
        }
        if not apply:
            return report
        for asset in missing_internal:
            ensure_internal_identifier(db, asset)
        for record in missing_legacy:
            db.add(
                AssetIdentifier(
                    asset_id=record.canonical_asset_id,
                    namespace=f"legacy_import:{record.import_batch_id}",
                    identifier_type="source_identifier",
                    identifier_value=record.source_identifier,
                    source_import_record_id=record.id,
                    verification_status="pending",
                    confidentiality="internal",
                )
            )
        for (legal_entity_id, asset_type_id), last_value in maximums.items():
            sequence = db.scalar(
                select(AssetCodeSequence).where(
                    AssetCodeSequence.legal_entity_id == legal_entity_id,
                    AssetCodeSequence.asset_type_id == asset_type_id,
                )
            )
            if sequence is None:
                db.add(
                    AssetCodeSequence(
                        legal_entity_id=legal_entity_id,
                        asset_type_id=asset_type_id,
                        last_value=last_value,
                    )
                )
            else:
                sequence.last_value = max(sequence.last_value, last_value)
        db.commit()
        return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write missing metadata after backup")
    args = parser.parse_args()
    print(json.dumps(build_report(args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
