# Microbial Colonies

A private colony-counting workspace. Each person signs in, uploads either one plate or a numbered set of frames, and gets boxes, a count, and a history that nobody else can open.

The detector is the YOLO weight in `best.pt`. A 7×4 mosaic uses the stage path from the imaging rig: even columns run top to bottom, odd columns run bottom to top.

## Run it locally

PostgreSQL:

```powershell
docker compose up -d db
```

Python dependencies, from `backend`:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or, from the project root, after the database is up: `.\run.ps1`

Open [http://localhost:8000](http://localhost:8000).

The API schema is at [http://localhost:8000/docs](http://localhost:8000/docs) while `ENV` is not `production`. Readiness is `GET /api/health` and `GET /api/ready`.

On startup the service applies database migrations, creates the administrator from `ADMIN_EMAIL` / `ADMIN_PASSWORD` if that email is new, and loads `best.pt`.

## Sign-in

Email and password are built in. Google appears when `GOOGLE_CLIENT_ID` is set. In the Google Cloud client, add `http://localhost:8000` as an authorized JavaScript origin.

Sessions use httpOnly cookies. An access cookie lasts 30 minutes and is refreshed from a rotating refresh cookie. Every analysis query is limited to the signed-in account.

Copy `.env.example` to `.env` if you do not already have one. A `.env` in the project root is read automatically. Do not commit it.

## What a run does

**Single plate.** One image. The model draws a box on each colony and stores the count.

**Mosaic.** Set the number of pictures, the rows, and the columns. Those three have to agree (`rows × columns = pictures`). Frames can be ordered by file name (`1`, `2`, `10`) or left in the order you dropped them. Placement is either row-by-row or the scanner path. Each frame is counted on its own, then the annotated frames are stitched. The plate total is the sum of the tiles, so overlapping edges are not removed.

Finished runs can be opened again, downloaded as CSV, or deleted. Deletes remove the files as well as the database rows.

Images are stored under `data/` and are only served back to the account that owns them.

## Deploy with Docker

The compose file runs Postgres and the API. The first image build downloads PyTorch, so it takes a while. One API process is intentional: the weights stay in memory, and runs are queued one at a time.

```powershell
docker compose up -d --build
```

Set `JWT_SECRET` to a long random value and `COOKIE_SECURE=true` behind HTTPS. Point `APP_ORIGIN` at the public origin, and add that origin in the Google client. Change the Postgres password in `docker-compose.yml` before this leaves one machine.

## Layout check

```powershell
cd backend
python -m pytest
```

That test locks the 7×4 scanner path to the stage order.
