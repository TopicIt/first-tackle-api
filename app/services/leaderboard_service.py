from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.models.catch_record import CatchRecord
from app.models.game_save import GameSave
from app.models.user import User
from app.services.catch_record_service import is_trophy_record, sync_catch_records_from_save


LEADERBOARD_LIMIT = 50
TROPHY_CATEGORIES = {"trophy", "very_rare", "legendary"}


def get_leaderboard(db: Session, board_type: str, *, fish_id: str | None = None) -> dict[str, Any]:
    normalized_type = normalize_board_type(board_type)
    saves = load_saves(db)
    source = "server-cloud-save"
    message = "Server leaderboard aggregated from latest cloud saves; records are not anti-cheat verified yet."

    if normalized_type == "trophies":
        rows, source, message = persistent_or_legacy_trophy_rows(db, saves)
    elif normalized_type in {"coins", "total-coins"}:
        rows = score_rows(saves, "coins")
    elif normalized_type in {"total-fish", "fish-caught"}:
        rows = score_rows(saves, "total-fish")
    elif normalized_type == "by-location":
        rows, source, message = persistent_or_legacy_fish_rows(db, saves)
    else:
        rows, source, message = persistent_or_legacy_fish_rows(db, saves, fish_id=fish_id)

    ranked_rows = add_ranks(rows[:LEADERBOARD_LIMIT])
    return {
        "ok": True,
        "type": f"species/{fish_id}/biggest" if fish_id else normalized_type,
        "source": source,
        "verified": False,
        "message": message,
        "records": ranked_rows,
        "rows": ranked_rows,
    }


def normalize_board_type(board_type: str) -> str:
    aliases = {
        "biggestFish": "biggest-fish",
        "biggest": "biggest-fish",
        "species": "biggest-fish",
        "coins": "coins",
        "totalCoins": "coins",
        "total-fish": "total-fish",
        "fishCaught": "total-fish",
        "byLocation": "by-location",
        "location": "by-location",
    }
    return aliases.get(board_type, board_type)


def load_saves(db: Session) -> list[GameSave]:
    return (
        db.query(GameSave)
        .options(joinedload(GameSave.user).joinedload(User.profile))
        .all()
    )


def load_catch_records(db: Session) -> list[CatchRecord]:
    return (
        db.query(CatchRecord)
        .options(joinedload(CatchRecord.user).joinedload(User.profile), joinedload(CatchRecord.user).joinedload(User.game_save))
        .filter(CatchRecord.active.is_(True))
        .all()
    )


def backfill_catch_records(db: Session, saves: list[GameSave]) -> None:
    for save in saves:
        sync_catch_records_from_save(db, save.user, save)
    if saves:
        db.commit()


def persistent_or_legacy_fish_rows(db: Session, saves: list[GameSave], *, fish_id: str | None = None) -> tuple[list[dict[str, Any]], str, str]:
    try:
        backfill_catch_records(db, saves)
        rows = fish_rows(load_catch_records(db), fish_id=fish_id)
        return rows, "server-catch-records", "Server leaderboard uses persistent catch records; records are not anti-cheat verified yet."
    except SQLAlchemyError:
        db.rollback()
        return legacy_fish_rows(saves, fish_id=fish_id), "server-cloud-save", "Persistent catch records are unavailable; leaderboard fell back to latest cloud saves."


def persistent_or_legacy_trophy_rows(db: Session, saves: list[GameSave]) -> tuple[list[dict[str, Any]], str, str]:
    try:
        backfill_catch_records(db, saves)
        rows = trophy_rows(load_catch_records(db))
        return rows, "server-catch-records", "Server leaderboard uses persistent catch records; records are not anti-cheat verified yet."
    except SQLAlchemyError:
        db.rollback()
        return legacy_trophy_rows(saves), "server-cloud-save", "Persistent catch records are unavailable; leaderboard fell back to latest cloud saves."


def fish_rows(records: list[CatchRecord], *, fish_id: str | None = None) -> list[dict[str, Any]]:
    rows = [
        catch_record_row(record)
        for record in records
        if fish_id is None or record.fish_id == fish_id
    ]
    return sorted(
        dedupe_rows(rows),
        key=lambda row: (row.get("weightGrams") or 0, row.get("serverRevision") or 0, row.get("serverUpdatedAt") or ""),
        reverse=True,
    )


def legacy_fish_rows(saves: list[GameSave], *, fish_id: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for save in saves:
        payload = save.payload_json if isinstance(save.payload_json, dict) else {}
        player_name = player_name_for_save(save, payload)
        rows.extend(fish_entry_row(save, player_name, entry) for entry in payload_fish_entries(payload, fish_id=fish_id))

        biggest = payload.get("stats", {}).get("biggestFish")
        if isinstance(biggest, dict) and (fish_id is None or biggest.get("fishId") == fish_id):
            rows.append(biggest_fish_row(save, player_name, biggest))

    return sorted(
        dedupe_rows(rows),
        key=lambda row: (row.get("weightGrams") or 0, row.get("serverRevision") or 0),
        reverse=True,
    )


def trophy_rows(records: list[CatchRecord]) -> list[dict[str, Any]]:
    rows = trophy_group_rows(records)
    return sorted(
        rows,
        key=lambda row: (
            row.get("trophyCount") or row.get("trophies") or 0,
            row.get("bestTrophyWeightGrams") or row.get("weightGrams") or 0,
            row.get("serverRevision") or 0,
        ),
        reverse=True,
    )


def legacy_trophy_rows(saves: list[GameSave]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for save in saves:
        payload = save.payload_json if isinstance(save.payload_json, dict) else {}
        player_name = player_name_for_save(save, payload)
        for entry in payload_trophy_entries(payload):
            row = fish_entry_row(save, player_name, entry)
            row["trophyCount"] = 1
            row["trophies"] = 1
            row["realTrophy"] = True
            rows.append(row)
    return sorted(
        dedupe_rows(rows),
        key=lambda row: (row.get("weightGrams") or 0, row.get("serverRevision") or 0),
        reverse=True,
    )


def catch_record_row(record: CatchRecord) -> dict[str, Any]:
    save = record.user.game_save
    payload = save.payload_json if save and isinstance(save.payload_json, dict) else {}
    player_name = player_name_for_user(record.user, payload)
    weight_grams = int(record.weight_grams or 0)
    return {
        **player_identity_fields_for_user(record.user, payload),
        "playerName": player_name,
        "fishId": record.fish_id,
        "fishName": record.fish_id,
        "weightKg": round(weight_grams / 1000, 3),
        "weightGrams": weight_grams,
        "locationId": record.water_id,
        "locationName": record.water_id or "unknown",
        "baitId": record.bait_id,
        "baitName": record.bait_id or "unknown",
        "depth": record.depth,
        "catchSpotId": record.cast_spot_id,
        "method": record.method,
        "tackleSummary": record.tackle_summary or "cloud save catch",
        "caughtAt": record.caught_at or record.caught_at_time or day_label(record.caught_at_day) or save_timestamp(save),
        "caughtAtDay": record.caught_at_day,
        "caughtAtTime": record.caught_at_time,
        "serverUpdatedAt": timestamp_value(record.source_updated_at or record.updated_at),
        "verified": False,
        "serverBacked": True,
        "source": "server-catch-records",
        "serverRevision": record.source_revision,
        "catchId": record.catch_id,
        "catchCategory": record.catch_category,
        "trophyTier": record.trophy_tier,
        "isTrophy": is_trophy_record(record),
        "totalFishCaught": score_for_payload(payload, "total-fish"),
        "level": payload.get("playerProfile", {}).get("level") if isinstance(payload.get("playerProfile"), dict) else None,
        "xp": payload.get("playerProfile", {}).get("xp") if isinstance(payload.get("playerProfile"), dict) else None,
    }


def score_rows(saves: list[GameSave], score_type: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for save in saves:
        payload = save.payload_json if isinstance(save.payload_json, dict) else {}
        player_name = player_name_for_save(save, payload)
        score = score_for_payload(payload, score_type)
        if score <= 0:
            continue
        rows.append(score_record(save, player_name, score_type, score))
    return sorted(rows, key=lambda row: (row["score"], row.get("serverRevision") or 0), reverse=True)


def payload_fish_entries(payload: dict[str, Any], *, fish_id: str | None = None) -> list[dict[str, Any]]:
    entries = payload.get("fishBasket")
    if not isinstance(entries, list):
        return []
    return [
        entry for entry in entries
        if isinstance(entry, dict)
        and entry.get("fishId")
        and numeric_value(entry.get("weightGrams")) > 0
        and (fish_id is None or entry.get("fishId") == fish_id)
    ]


def player_name_for_save(save: GameSave, payload: dict[str, Any]) -> str:
    profile = getattr(save.user, "profile", None)
    payload_profile = payload.get("playerProfile") if isinstance(payload.get("playerProfile"), dict) else {}
    return (
        getattr(profile, "display_name", None)
        or payload_profile.get("name")
        or payload_profile.get("playerName")
        or save.user.email.split("@")[0]
    )


def fish_entry_row(save: GameSave, player_name: str, entry: dict[str, Any]) -> dict[str, Any]:
    weight_grams = int(numeric_value(entry.get("weightGrams")))
    row = {
        **player_identity_fields(save, save.payload_json if isinstance(save.payload_json, dict) else {}),
        "playerName": player_name,
        "fishId": entry.get("fishId"),
        "fishName": entry.get("fishId"),
        "weightKg": round(weight_grams / 1000, 3),
        "weightGrams": weight_grams,
        "locationId": entry.get("waterId") or entry.get("locationId"),
        "locationName": entry.get("waterId") or entry.get("locationId") or "unknown",
        "baitId": entry.get("bait") or entry.get("baitId"),
        "baitName": entry.get("bait") or entry.get("baitId") or "unknown",
        "depth": entry.get("depth"),
        "catchSpotId": entry.get("catchSpotId"),
        "method": entry.get("method"),
        "tackleSummary": tackle_summary(entry),
        "caughtAt": caught_at(entry, save),
        "caughtAtDay": numeric_int_or_none(entry.get("caughtAtDay")),
        "caughtAtTime": entry.get("caughtAtTime"),
        "serverUpdatedAt": save_timestamp(save),
        "verified": False,
        "serverBacked": True,
        "source": "server-cloud-save",
        "serverRevision": save.revision,
        "totalFishCaught": score_for_payload(save.payload_json, "total-fish"),
    }
    return row


def biggest_fish_row(save: GameSave, player_name: str, biggest: dict[str, Any]) -> dict[str, Any]:
    weight_grams = int(numeric_value(biggest.get("weightGrams")))
    return {
        **player_identity_fields(save, save.payload_json if isinstance(save.payload_json, dict) else {}),
        "playerName": player_name,
        "fishId": biggest.get("fishId"),
        "fishName": biggest.get("fishId"),
        "weightKg": round(weight_grams / 1000, 3),
        "weightGrams": weight_grams,
        "locationId": biggest.get("waterId") or biggest.get("locationId") or biggest.get("biggestFishWaterId"),
        "locationName": biggest.get("waterId") or biggest.get("locationId") or biggest.get("biggestFishWaterId") or "unknown",
        "baitId": biggest.get("bait") or biggest.get("baitId"),
        "baitName": biggest.get("bait") or biggest.get("baitId"),
        "depth": biggest.get("depth"),
        "catchSpotId": biggest.get("catchSpotId"),
        "method": biggest.get("method"),
        "tackleSummary": tackle_summary(biggest),
        "caughtAt": day_label(biggest.get("caughtAtDay")) or save_timestamp(save),
        "caughtAtDay": numeric_int_or_none(biggest.get("caughtAtDay")),
        "caughtAtTime": biggest.get("caughtAtTime"),
        "serverUpdatedAt": save_timestamp(save),
        "verified": False,
        "serverBacked": True,
        "source": "server-cloud-save",
        "serverRevision": save.revision,
        "totalFishCaught": score_for_payload(save.payload_json, "total-fish"),
    }


def score_record(save: GameSave, player_name: str, score_type: str, score: int) -> dict[str, Any]:
    return {
        **player_identity_fields(save, save.payload_json if isinstance(save.payload_json, dict) else {}),
        "playerName": player_name,
        "fishId": None,
        "fishName": None,
        "weightKg": None,
        "weightGrams": None,
        "locationId": None,
        "locationName": "all waters",
        "baitId": None,
        "baitName": None,
        "tackleSummary": f"{score} {score_type}",
        "caughtAt": save_timestamp(save),
        "serverUpdatedAt": save_timestamp(save),
        "verified": False,
        "serverBacked": True,
        "source": "server-cloud-save",
        "serverRevision": save.revision,
        "score": score,
        "coins": score if score_type == "coins" else None,
        "totalFishCaught": score if score_type == "total-fish" else score_for_payload(save.payload_json, "total-fish"),
        "trophies": score if score_type == "trophies" else None,
    }


def score_for_payload(payload: dict[str, Any], score_type: str) -> int:
    if not isinstance(payload, dict):
        return 0
    profile = payload.get("playerProfile") if isinstance(payload.get("playerProfile"), dict) else {}
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    if score_type == "coins":
        return int(numeric_value(profile.get("totalCoinsEarned") or stats.get("totalCoinsEarned") or payload.get("money")))
    if score_type == "total-fish":
        journal_total = 0
        journal = payload.get("catchJournal")
        if isinstance(journal, dict):
            journal_total = sum(int(numeric_value(entry.get("totalCaught"))) for entry in journal.values() if isinstance(entry, dict))
        return max(
            int(numeric_value(profile.get("fishCaughtTotal"))),
            int(numeric_value(stats.get("totalFishCaught") or stats.get("fishCaughtTotal"))),
            journal_total,
            len(payload.get("fishBasket") or []),
        )
    return 0


def is_trophy_entry(entry: dict[str, Any]) -> bool:
    return (
        bool(entry.get("trophyTier"))
        or bool(entry.get("tier"))
        or entry.get("trophy") is True
        or entry.get("isTrophy") is True
        or numeric_value(entry.get("stars") or entry.get("trophyStars")) > 0
        or str(entry.get("key") or "").startswith("trophyTier")
        or entry.get("catchCategory") in TROPHY_CATEGORIES
    )


def trophy_group_rows(records: list[CatchRecord]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[CatchRecord]] = {}
    for record in records:
        if not is_trophy_record(record):
            continue
        grouped.setdefault((record.user_id, record.fish_id), []).append(record)

    rows: list[dict[str, Any]] = []
    for (_user_id, fish_id), trophies in grouped.items():
        first = trophies[0]
        save = first.user.game_save
        payload = save.payload_json if save and isinstance(save.payload_json, dict) else {}
        player_name = player_name_for_user(first.user, payload)
        sorted_trophies = sorted(trophies, key=lambda entry: entry.weight_grams or 0, reverse=True)
        best = sorted_trophies[0]
        best_weight = int(best.weight_grams or 0)
        recent = sorted(trophies, key=lambda entry: entry.caught_at_day or 0, reverse=True)[0]
        rows.append({
            **player_identity_fields_for_user(first.user, payload),
            "playerName": player_name,
            "fishId": fish_id,
            "fishName": fish_id,
            "weightKg": round(best_weight / 1000, 3) if best_weight else None,
            "weightGrams": best_weight or None,
            "bestTrophyWeightKg": round(best_weight / 1000, 3) if best_weight else None,
            "bestTrophyWeightGrams": best_weight,
            "locationId": best.water_id,
            "locationName": best.water_id or "unknown",
            "baitId": best.bait_id,
            "baitName": best.bait_id,
            "depth": best.depth,
            "catchSpotId": best.cast_spot_id,
            "method": best.method,
            "tackleSummary": f"{len(trophies)} trophies",
            "caughtAt": recent.caught_at or recent.caught_at_time or day_label(recent.caught_at_day) or save_timestamp(save),
            "caughtAtDay": recent.caught_at_day,
            "caughtAtTime": recent.caught_at_time,
            "serverUpdatedAt": timestamp_value(recent.source_updated_at or recent.updated_at),
            "verified": False,
            "serverBacked": True,
            "source": "server-catch-records",
            "serverRevision": recent.source_revision,
            "totalFishCaught": score_for_payload(payload, "total-fish"),
            "trophyCount": len(trophies),
            "trophies": len(trophies),
            "realTrophy": True,
            "topTrophies": [
                normalize_trophy_record_entry(entry)
                for entry in sorted_trophies[:10]
            ],
        })
    return rows


def normalize_trophy_record_entry(record: CatchRecord) -> dict[str, Any]:
    return {
        "fishId": record.fish_id,
        "weightGrams": int(record.weight_grams or 0),
        "caughtAtDay": record.caught_at_day,
        "caughtAtTime": record.caught_at_time,
        "waterId": record.water_id,
        "bait": record.bait_id,
        "depth": record.depth,
        "catchSpotId": record.cast_spot_id,
        "trophyTier": record.trophy_tier,
        "catchCategory": record.catch_category,
    }


def payload_trophy_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    raw_trophies = payload.get("trophies")
    if isinstance(raw_trophies, list):
        entries.extend(entry for entry in raw_trophies if isinstance(entry, dict) and is_trophy_entry(entry))
    entries.extend(entry for entry in payload_fish_entries(payload) if is_trophy_entry(entry))
    return dedupe_trophy_entries(entries)


def normalize_trophy_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "fishId": entry.get("fishId"),
        "weightGrams": int(numeric_value(entry.get("weightGrams"))),
        "caughtAtDay": numeric_int_or_none(entry.get("caughtAtDay")),
        "caughtAtTime": entry.get("caughtAtTime"),
        "waterId": entry.get("waterId") or entry.get("locationId"),
        "bait": entry.get("bait") or entry.get("baitId"),
        "depth": entry.get("depth"),
        "catchSpotId": entry.get("catchSpotId"),
        "trophyTier": entry.get("trophyTier") or entry.get("tier"),
        "catchCategory": entry.get("catchCategory"),
    }


def dedupe_trophy_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for entry in entries:
        key = (
            entry.get("fishId"),
            int(numeric_value(entry.get("weightGrams"))),
            entry.get("caughtAtDay"),
            entry.get("caughtAtTime"),
            entry.get("trophyTier") or entry.get("tier") or entry.get("key"),
        )
        deduped[key] = entry
    return list(deduped.values())


def player_identity_fields(save: GameSave, payload: dict[str, Any]) -> dict[str, Any]:
    profile = getattr(save.user, "profile", None)
    payload_profile = payload.get("playerProfile") if isinstance(payload.get("playerProfile"), dict) else {}
    return {
        "playerId": save.user_id,
        "displayName": player_name_for_save(save, payload),
        "avatarId": getattr(profile, "avatar_id", None) or payload_profile.get("avatarId") or payload_profile.get("avatar"),
        "avatar": getattr(profile, "avatar_id", None) or payload_profile.get("avatar") or payload_profile.get("avatarId"),
        "avatarType": "custom" if (getattr(profile, "avatar_custom_url", None) or payload_profile.get("customAvatarDataUrl")) else "preset",
        "customAvatarDataUrl": getattr(profile, "avatar_custom_url", None) or payload_profile.get("customAvatarDataUrl"),
    }


def player_name_for_user(user: User, payload: dict[str, Any]) -> str:
    profile = getattr(user, "profile", None)
    payload_profile = payload.get("playerProfile") if isinstance(payload.get("playerProfile"), dict) else {}
    return (
        getattr(profile, "display_name", None)
        or payload_profile.get("name")
        or payload_profile.get("playerName")
        or user.email.split("@")[0]
    )


def player_identity_fields_for_user(user: User, payload: dict[str, Any]) -> dict[str, Any]:
    profile = getattr(user, "profile", None)
    payload_profile = payload.get("playerProfile") if isinstance(payload.get("playerProfile"), dict) else {}
    return {
        "playerId": user.id,
        "displayName": player_name_for_user(user, payload),
        "avatarId": getattr(profile, "avatar_id", None) or payload_profile.get("avatarId") or payload_profile.get("avatar"),
        "avatar": getattr(profile, "avatar_id", None) or payload_profile.get("avatar") or payload_profile.get("avatarId"),
        "avatarType": "custom" if (getattr(profile, "avatar_custom_url", None) or payload_profile.get("customAvatarDataUrl")) else "preset",
        "customAvatarDataUrl": getattr(profile, "avatar_custom_url", None) or payload_profile.get("customAvatarDataUrl"),
    }


def tackle_summary(entry: dict[str, Any]) -> str:
    parts = [
        entry.get("method"),
        entry.get("depth"),
        entry.get("catchSpotId"),
    ]
    return " / ".join(str(part) for part in parts if part) or "cloud save catch"


def caught_at(entry: dict[str, Any], save: GameSave) -> str:
    return (
        entry.get("caughtAt")
        or entry.get("caughtAtTime")
        or day_label(entry.get("caughtAtDay"))
        or save_timestamp(save)
    )


def save_timestamp(save: GameSave) -> str:
    if save is None:
        return "server catch record"
    value = save.client_updated_at or save.server_updated_at or save.created_at
    if isinstance(value, datetime):
        return value.isoformat()
    return "server cloud save"


def timestamp_value(value: datetime | None) -> str:
    return value.isoformat() if isinstance(value, datetime) else "server catch record"


def day_label(value: Any) -> str | None:
    if value is None:
        return None
    return f"day {value}"


def numeric_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def numeric_int_or_none(value: Any) -> int | None:
    number = numeric_value(value)
    return int(number) if number else None


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row.get("playerName"),
            row.get("fishId"),
            row.get("weightGrams"),
            row.get("caughtAt"),
        )
        previous = deduped.get(key)
        if previous is None or (row.get("serverRevision") or 0) > (previous.get("serverRevision") or 0):
            deduped[key] = row
    return list(deduped.values())


def add_ranks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**row, "rank": index + 1} for index, row in enumerate(rows)]
