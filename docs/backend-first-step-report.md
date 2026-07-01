# First backend step report

## Implemented

- FastAPI project skeleton in `first-tackle-api`.
- PostgreSQL-ready SQLAlchemy models:
  - `users`
  - `player_profiles`
  - `game_saves`
- Alembic setup with initial migration.
- Pydantic settings using `.env`.
- CORS configuration for local Vite and GitHub Pages.
- Email/password auth foundation.
- bcrypt password hashing.
- JWT access and refresh tokens.
- Auth endpoints:
  - `POST /auth/register`
  - `POST /auth/login`
  - `POST /auth/refresh`
- Profile endpoints:
  - `GET /profile/me`
  - `PATCH /profile/me`
- Cloud save endpoints:
  - `GET /save/load`
  - `POST /save/sync`
  - `GET /save/status`
- Revision-based save conflict behavior.
- Railway-oriented README and `.env.example`.

## Intentionally not implemented yet

- Google OAuth.
- Email verification.
- Password reset flow.
- Leaderboards.
- Full game logic on backend.
- Cast result generation.
- Economy/reward validation.
- Complex save merge.
- Required login for gameplay.

## Next steps

1. Deploy backend to Railway.
2. Connect frontend login UI.
3. Add manual cloud save upload/download in settings or profile.
4. Add Google auth after email login is stable.
5. Add leaderboards after catch/trophy records are server-verifiable.

## Notes

The first backend should support cloud save without slowing gameplay iteration. The frontend should remain playable without an account until server sync is stable.
