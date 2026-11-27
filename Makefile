# Doodle with Pip. Run it: `make up` (Docker only, http://localhost:8080). Agents: see CLAUDE.md.
# Everything below `down` is for working on the code (Python 3.9+ and Node 20+).
PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

.PHONY: up down setup dev stop backend frontend eval test check last-game tavus-setup tavus-update build docker

up:               ## THE one command: build + run the whole app in Docker -> http://localhost:8080
	@test -f .env || cp .env.example .env
	docker compose up --build

down:             ## stop it
	docker compose down

setup:            ## install backend (venv) + frontend deps
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -r backend/requirements.txt
	cd frontend && npm install
	@test -f .env || cp .env.example .env
	@echo "Ready. Run: make dev   (demo mode until TAVUS_API_KEY is set in .env)"

dev:              ## backend on :8000 + frontend on :5173 (open http://localhost:5173)
	@trap 'kill 0' INT TERM; \
	$(BIN)/uvicorn backend.app:app --reload --port 8000 & \
	(cd frontend && npm run dev) & \
	wait

stop:             ## free ports 8000 + 5173 if a previous `make dev` left something running
	-@lsof -ti tcp:8000 -ti tcp:5173 -sTCP:LISTEN | xargs kill -9 2>/dev/null; echo "ports 8000 and 5173 are free"

backend:
	$(BIN)/uvicorn backend.app:app --reload --port 8000

frontend:
	cd frontend && npm run dev

eval:             ## golden-set eval (game logic), prints pass/fail
	$(BIN)/python backend/evals/run_evals.py -v

test:             ## API tests
	$(BIN)/python -m pytest backend/tests -q

check: eval test  ## everything an agent should run after a change
	cd frontend && npm run build

last-game:        ## what happened in the latest game: rounds, every guess, latency (from the DB)
	$(BIN)/python -m backend.inspect_game

tavus-setup:      ## optional: the server sets Pip up on startup; this does the same by hand
	$(BIN)/python -m backend.setup_tavus

tavus-update:     ## optional: same as tavus-setup (find or create Pip, sync it to the code)
	$(BIN)/python -m backend.setup_tavus --update

build:            ## production frontend build (served by FastAPI from frontend/dist)
	cd frontend && npm run build

docker:           ## run the production image locally on http://localhost:8080
	docker build -t doodle-with-pip . && docker run --rm -p 8080:8000 --env-file .env doodle-with-pip
