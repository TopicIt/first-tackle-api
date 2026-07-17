from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catch_record import CatchRecord
from app.models.game_save import GameSave
from app.models.user import User


TROPHY_CATEGORIES = {"trophy", "very_rare", "legendary"}
FISH_ID_ALIASES = {
    "perch": "okun",
}


def sync_catch_records_from_save(db: Session, user: User, game_save: GameSave) -> int:
    payload = game_save.payload_json if isinstance(game_save.payload_json, dict) else {}
    if is_explicit_reset_payload(payload):
        deactivate_user_catch_records(db, user.id)
        return 0

    synced_ids, _rejected = sync_catch_entries(
        db,
        user,
        extract_catch_entries(payload),
        source_revision=game_save.revision,
        source_updated_at=game_save.client_updated_at or game_save.server_updated_at,
    )
    return len(synced_ids)


def sync_catch_entries(
    db: Session,
    user: User,
    entries: list[dict[str, Any]],
    *,
    source_revision: int | None = None,
    source_updated_at: datetime | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    synced_ids, rejected, _results = sync_catch_entries_with_results(
        db,
        user,
        entries,
        source_revision=source_revision,
        source_updated_at=source_updated_at,
    )
    return synced_ids, rejected


def sync_catch_entries_with_results(
    db: Session,
    user: User,
    entries: list[dict[str, Any]],
    *,
    source_revision: int | None = None,
    source_updated_at: datetime | None = None,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    synced_ids: list[str] = []
    rejected: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for entry in dedupe_extracted_entries([entry for entry in entries if isinstance(entry, dict)]):
        requested_catch_id = normalized_string(entry.get("catchId") or entry.get("id"))
        normalized = normalize_catch_entry(
            user,
            entry,
            source_revision=source_revision,
            source_updated_at=source_updated_at,
        )
        if not normalized:
            rejected_entry = {
                "catchId": requested_catch_id,
                "reason": "invalid-catch",
            }
            rejected.append(rejected_entry)
            results.append({
                "catchId": requested_catch_id,
                "status": "rejected",
                "reason": "invalid-catch",
            })
            continue
        _record, status = upsert_catch_record_with_status(db, normalized)
        acknowledged_id = normalized["catch_id"] or normalized["catch_key"]
        synced_ids.append(acknowledged_id)
        results.append({
            "catchId": acknowledged_id,
            "status": status,
        })
    return synced_ids, rejected, results


def deactivate_user_catch_records(db: Session, user_id: str) -> int:
    records = db.scalars(
        select(CatchRecord)
        .where(CatchRecord.user_id == user_id)
        .where(CatchRecord.active.is_(True))
    ).all()
    for record in records:
        record.active = False
        db.add(record)
    return len(records)


def extract_catch_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for source in ("catchHistory", "fishBasket", "trophies"):
        raw_entries = payload.get(source)
        if not isinstance(raw_entries, list):
            continue
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                continue
            if not raw_entry.get("fishId") or normalized_weight_grams(raw_entry) <= 0:
                continue
            entries.append({**raw_entry, "_source": source})
    return dedupe_extracted_entries(entries)


def dedupe_extracted_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_priority = {
        "catchHistory": 3,
        "fishBasket": 2,
        "trophies": 1,
    }
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for entry in entries:
        key = (
            entry.get("catchId") or entry.get("id"),
            normalize_fish_id(entry.get("fishId")),
            normalized_weight_grams(entry),
            entry.get("caughtAtDay"),
            entry.get("caughtAtTime"),
            entry.get("trophyTier") or entry.get("tier"),
        )
        previous = deduped.get(key)
        if previous is None or source_priority.get(entry.get("_source"), 0) >= source_priority.get(previous.get("_source"), 0):
            deduped[key] = entry
    return list(deduped.values())


def normalize_catch_entry(
    user: User,
    entry: dict[str, Any],
    *,
    source_revision: int | None = None,
    source_updated_at: datetime | None = None,
) -> dict[str, Any] | None:
    fish_id = normalize_fish_id(entry.get("fishId"))
    weight_grams = normalized_weight_grams(entry)
    if not fish_id or weight_grams <= 0:
        return None

    catch_id = normalized_string(entry.get("catchId") or entry.get("id"))
    catch_key = catch_key_for_entry(user.id, catch_id, entry)
    trophy_tier = normalized_string(entry.get("trophyTier") or entry.get("tier"))
    catch_category = normalized_string(entry.get("catchCategory"))
    water_id = normalized_string(entry.get("waterId") or entry.get("locationId"))
    bait_id = normalized_string(entry.get("bait") or entry.get("baitId"))
    method = normalized_string(entry.get("method"))
    depth = normalized_string(entry.get("depth"))
    cast_spot_id = normalized_string(entry.get("catchSpotId") or entry.get("spotId"))

    return {
        "user_id": user.id,
        "catch_key": catch_key,
        "catch_id": catch_id,
        "fish_id": fish_id,
        "weight_grams": weight_grams,
        "catch_category": catch_category,
        "trophy_tier": trophy_tier,
        "water_id": water_id,
        "bait_id": bait_id,
        "method": method,
        "tackle_summary": tackle_summary(entry),
        "depth": depth,
        "cast_spot_id": cast_spot_id,
        "caught_at_day": numeric_int_or_none(entry.get("caughtAtDay")),
        "caught_at_time": normalized_string(entry.get("caughtAtTime")),
        "caught_at": normalized_string(entry.get("caughtAt")),
        "source_revision": source_revision,
        "source_updated_at": source_updated_at,
        "raw_json": {
            key: value
            for key, value in entry.items()
            if not key.startswith("_")
        },
    }


def upsert_catch_record(db: Session, values: dict[str, Any]) -> CatchRecord:
    record, _status = upsert_catch_record_with_status(db, values)
    return record


def upsert_catch_record_with_status(db: Session, values: dict[str, Any]) -> tuple[CatchRecord, str]:
    existing = db.scalar(
        select(CatchRecord)
        .where(CatchRecord.user_id == values["user_id"])
        .where(CatchRecord.catch_key == values["catch_key"])
    )
    if existing is None:
        record = CatchRecord(**values, active=True)
        status = "inserted"
    else:
        record = existing
        for key, value in values.items():
            setattr(record, key, value)
        record.active = True
        status = "already_exists"
    db.add(record)
    return record, status


def is_explicit_reset_payload(payload: dict[str, Any]) -> bool:
    tombstone = payload.get("resetTombstone")
    if isinstance(tombstone, dict) and tombstone.get("resetAt"):
        return True
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return bool(metadata.get("resetTombstone") or metadata.get("resetAt"))


def is_trophy_record(record: CatchRecord) -> bool:
    return bool(
        record.trophy_tier
        or record.catch_category in TROPHY_CATEGORIES
        or (record.raw_json or {}).get("isTrophy") is True
        or (record.raw_json or {}).get("trophy") is True
    )


def catch_key_for_entry(user_id: str, catch_id: str | None, entry: dict[str, Any]) -> str:
    if catch_id:
        return f"id:{catch_id}"[:96]
    basis = "|".join([
        user_id,
        normalize_fish_id(entry.get("fishId")),
        str(int(numeric_value(entry.get("weightGrams")))),
        str(entry.get("caughtAtDay") or ""),
        str(entry.get("caughtAtTime") or entry.get("caughtAt") or ""),
        str(entry.get("waterId") or entry.get("locationId") or ""),
        str(entry.get("bait") or entry.get("baitId") or ""),
    ])
    return f"hash:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:48]}"


def normalize_fish_id(value: Any) -> str:
    fish_id = str(value or "").strip()
    return FISH_ID_ALIASES.get(fish_id, fish_id)


def tackle_summary(entry: dict[str, Any]) -> str | None:
    parts = [
        entry.get("method"),
        entry.get("depth"),
        entry.get("catchSpotId") or entry.get("spotId"),
    ]
    summary = " / ".join(str(part) for part in parts if part)
    return summary or None


def normalized_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def numeric_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def numeric_int_or_none(value: Any) -> int | None:
    number = numeric_value(value)
    return int(number) if number else None


def normalized_weight_grams(entry: dict[str, Any]) -> int:
    weight_grams = numeric_value(entry.get("weightGrams"))
    if weight_grams > 0:
        return int(weight_grams)
    weight_kg = numeric_value(entry.get("weightKg"))
    if weight_kg > 0:
        return int(round(weight_kg * 1000))
    weight = numeric_value(entry.get("weight"))
    if weight <= 0:
        return 0
    return int(round(weight * 1000)) if weight <= 20 else int(round(weight))
