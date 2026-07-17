import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-access-secret")
os.environ.setdefault("JWT_REFRESH_SECRET", "test-refresh-secret")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.catch_record import CatchRecord
from app.models.game_save import GameSave
from app.models.profile import PlayerProfile
from app.models.user import User
from app.schemas.profile import ProfileUpdateRequest
from app.schemas.save import SaveSyncRequest
from app.services.leaderboard_service import get_leaderboard
from app.services.save_service import sync_save


class ProfileSaveLeaderboardTests(unittest.TestCase):
    def make_engine(self):
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    def create_user(self, db: Session, name: str = "Старе ім'я") -> User:
        user = User(email="profile-test@example.invalid", password_hash="test")
        user.profile = PlayerProfile(display_name=name, language="uk")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def save_request(self, revision: int, *, force: bool = False, reset: bool = False) -> SaveSyncRequest:
        payload = {
            "playerProfile": {"name": "Старе ім'я", "level": 4, "xp": 120},
            "fishBasket": [{
                "id": "catch-stable-1",
                "fishId": "carp",
                "weightGrams": 1450,
                "waterId": "greada",
                "caughtAt": "2026-07-17T10:00:00Z",
            }],
        }
        if reset:
            payload["resetTombstone"] = {"resetAt": "2026-07-17T11:00:00Z"}
        return SaveSyncRequest(
            saveVersion=1,
            revision=revision,
            force=force,
            payload=payload,
        )

    def test_profile_name_is_trimmed_and_empty_name_is_rejected(self):
        self.assertEqual(ProfileUpdateRequest(displayName="  Нове ім'я  ").display_name, "Нове ім'я")
        with self.assertRaises(ValueError):
            ProfileUpdateRequest(displayName="   ")

    def test_save_survives_when_catch_record_table_is_missing(self):
        engine = self.make_engine()
        User.__table__.create(engine)
        PlayerProfile.__table__.create(engine)
        GameSave.__table__.create(engine)
        with Session(engine, expire_on_commit=False) as db:
            user = self.create_user(db)
            response = sync_save(db, user, self.save_request(0))
            self.assertEqual(response.metadata.revision, 1)
            self.assertEqual(db.scalar(select(GameSave.revision)), 1)

    def test_save_survives_non_database_catch_sync_failure(self):
        engine = self.make_engine()
        Base.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as db:
            user = self.create_user(db)
            with patch(
                "app.services.save_service.sync_catch_records_from_save",
                side_effect=RuntimeError("optional catch sync failed"),
            ):
                response = sync_save(db, user, self.save_request(0))
            self.assertEqual(response.metadata.revision, 1)
            self.assertEqual(db.scalar(select(GameSave.revision)), 1)

    def test_rename_overlays_existing_deduped_catch_records(self):
        engine = self.make_engine()
        Base.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as db:
            user = self.create_user(db)
            sync_save(db, user, self.save_request(0))
            db.expire_all()
            user = db.scalar(select(User).where(User.email == "profile-test@example.invalid"))
            sync_save(db, user, self.save_request(1, force=True))
            self.assertEqual(db.query(CatchRecord).count(), 1)

            user.profile.display_name = "Нове українське ім'я"
            db.commit()
            board = get_leaderboard(db, "biggest-fish")
            self.assertEqual(board["source"], "server-catch-records")
            self.assertEqual(board["records"][0]["playerName"], "Нове українське ім'я")

            db.expire_all()
            user = db.scalar(select(User).where(User.email == "profile-test@example.invalid"))
            sync_save(db, user, self.save_request(2, force=True, reset=True))
            self.assertEqual(db.query(CatchRecord).filter(CatchRecord.active.is_(True)).count(), 0)

    def test_leaderboard_keeps_utf8_names_and_readable_labels(self):
        engine = self.make_engine()
        Base.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as db:
            user = self.create_user(db, name="\u0406\u0432\u0430\u0441\u0438\u043a \u0422\u0435\u043b\u0435\u0441\u0438\u043a")
            payload = SaveSyncRequest(
                saveVersion=1,
                revision=0,
                payload={
                    "playerProfile": {"name": "\u0406\u0432\u0430\u0441\u0438\u043a \u0422\u0435\u043b\u0435\u0441\u0438\u043a", "level": 2, "xp": 45},
                    "catchHistory": [{
                        "catchId": "utf8-catch-1",
                        "fishId": "carp",
                        "weightGrams": 1330,
                        "caughtAtDay": 1,
                    }],
                    "fishBasket": [],
                },
            )
            sync_save(db, user, payload)

            board = get_leaderboard(db, "biggest-fish")
            self.assertEqual(board["records"][0]["playerName"], "\u0406\u0432\u0430\u0441\u0438\u043a \u0422\u0435\u043b\u0435\u0441\u0438\u043a")
            self.assertEqual(board["records"][0]["caughtAt"], "\u0414\u0435\u043d\u044c 1")
            self.assertIsNone(board["records"][0]["tackleSummary"])

    def test_corrupted_placeholder_name_falls_back_to_valid_payload_name(self):
        engine = self.make_engine()
        Base.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as db:
            user = self.create_user(db, name="????? ??????????? ???????")
            payload = SaveSyncRequest(
                saveVersion=1,
                revision=0,
                payload={
                    "playerProfile": {"name": "\u041c\u0430\u0440\u0456\u0447\u043a\u0430", "level": 2, "xp": 45},
                    "catchHistory": [{
                        "catchId": "utf8-catch-2",
                        "fishId": "rotan",
                        "weightGrams": 140,
                        "caughtAt": "2026-07-17T10:00:00Z",
                    }],
                    "fishBasket": [],
                },
            )
            sync_save(db, user, payload)

            board = get_leaderboard(db, "biggest-fish")
            self.assertEqual(board["records"][0]["playerName"], "\u041c\u0430\u0440\u0456\u0447\u043a\u0430")


class CatchHistorySyncTests(unittest.TestCase):
    def make_engine(self):
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    def create_user(self, db: Session) -> User:
        user = User(email="catch-history@example.invalid", password_hash="test")
        user.profile = PlayerProfile(display_name="Тестовий рибалка", language="uk")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def test_catch_history_survives_keepnet_sale_and_dedupes_repeated_sync(self):
        engine = self.make_engine()
        Base.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as db:
            user = self.create_user(db)
            first_payload = SaveSyncRequest(
                saveVersion=1,
                revision=0,
                payload={
                    "playerProfile": {"name": "Тестовий рибалка", "level": 4, "xp": 120},
                    "catchHistory": [{
                        "catchId": "catch-stable-1",
                        "fishId": "carp",
                        "weightGrams": 1450,
                        "waterId": "greada",
                        "caughtAt": "2026-07-17T10:00:00Z",
                    }],
                    "fishBasket": [{
                        "id": "catch-stable-1",
                        "fishId": "carp",
                        "weightGrams": 1450,
                        "waterId": "greada",
                        "caughtAt": "2026-07-17T10:00:00Z",
                    }],
                },
            )
            sync_save(db, user, first_payload)
            self.assertEqual(db.query(CatchRecord).count(), 1)
            db.expire_all()
            user = db.scalar(select(User).where(User.email == "catch-history@example.invalid"))

            second_payload = SaveSyncRequest(
                saveVersion=1,
                revision=1,
                force=True,
                payload={
                    "playerProfile": {"name": "Тестовий рибалка", "level": 4, "xp": 120},
                    "catchHistory": [{
                        "catchId": "catch-stable-1",
                        "fishId": "carp",
                        "weightGrams": 1450,
                        "waterId": "greada",
                        "caughtAt": "2026-07-17T10:00:00Z",
                    }],
                    "fishBasket": [],
                },
            )
            sync_save(db, user, second_payload)

            records = db.query(CatchRecord).all()
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].active)
            self.assertEqual(records[0].catch_id, "catch-stable-1")


if __name__ == "__main__":
    unittest.main()
