# Reverse Pictionary. `make setup` once, then `make dev`.
PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

.PHONY: setup dev stop backend frontend eval test check tavus-setup tavus-update build docker

setup:            ## install backend (venv) + frontend deps
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -r backend/requirements.txt
	cd frontend && npm install
	@test -f .env || cp .env.example .env
	@echo "Ready. Run: make dev   (demo mode until TAVUS_API_KEY + TAVUS_PAL_ID are set in .env)"

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

tavus-setup:      ## one-time: create the PAL + tools on Tavus, prints TAVUS_PAL_ID
	$(BIN)/python -m backend.setup_tavus

tavus-update:     ## after changing Pip's prompt or settings: update the PAL in TAVUS_PAL_ID in place
	$(BIN)/python -m backend.setup_tavus --update

build:            ## production frontend build (served by FastAPI from frontend/dist)
	cd frontend && npm run build

docker:           ## run the production image locally on :8000
	docker build -t reverse-pictionary . && docker run --rm -p 8000:8000 --env-file .env reverse-pictionary
