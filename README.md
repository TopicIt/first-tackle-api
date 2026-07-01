# First Tackle API

FastAPI backend skeleton for First Tackle accounts, profiles, and cloud saves.

This first backend step intentionally does not move full fishing gameplay logic to the server. The frontend can still run without login or backend access.

## Stack

- Python 3.12+
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Pydantic settings
- JWT access/refresh tokens
- bcrypt password hashing

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set real secrets.

For local smoke testing without PostgreSQL, you can temporarily set:

```env
DATABASE_URL=sqlite:///./first_tackle_dev.db
```

PostgreSQL is the production target.

## Migrations

```powershell
alembic upgrade head
```

Create a new migration later with:

```powershell
alembic revision --autogenerate -m "message"
```

## Run Locally

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

## Required Env Vars

- `DATABASE_URL`
- `JWT_SECRET`
- `JWT_REFRESH_SECRET`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `CORS_ORIGINS`

Default local CORS origins:

- `http://localhost:5173`
- `http://127.0.0.1:5173`
- `https://topicit.github.io`

## API Overview

### Health

- `GET /health`

### Auth

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`

### Profile

- `GET /profile/me`
- `PATCH /profile/me`

### Save

- `GET /save/load`
- `POST /save/sync`
- `GET /save/status`

## Save Sync Rules

- If the user has no server save, `POST /save/sync` creates revision `1`.
- If incoming `revision` matches the current server revision, the save is accepted and the server increments revision.
- If incoming `revision` is older or different, the API returns `409 Conflict` with server revision metadata.
- No merge logic exists yet.

## Railway Deployment

1. Create a new Railway project.
2. Add a PostgreSQL service.
3. Add this API service from GitHub or deploy from the repo.
4. Set env vars:
   - `DATABASE_URL`
   - `JWT_SECRET`
   - `JWT_REFRESH_SECRET`
   - `ACCESS_TOKEN_EXPIRE_MINUTES`
   - `REFRESH_TOKEN_EXPIRE_DAYS`
   - `CORS_ORIGINS`
5. Run migrations:
   ```powershell
   alembic upgrade head
   ```
6. Start command:
   ```text
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

## Not Implemented Yet

- Google OAuth
- email verification
- password reset email sending
- leaderboards
- server-owned cast result generation
- reward/economy validation
- save merge conflict UI

