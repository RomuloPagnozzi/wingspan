# Deploy and operate the web app on a server you can SSH into (behind Cloudflare Tunnel + Access).
# The server is DEPLOY_HOST in .env (gitignored; see .env.example).
#   make setup              once: /srv/wingspan, its .env (fill in the Cloudflare values), nightly backups
#   make deploy             build for the server's CPU (amd64), ship the image over SSH, restart
#   make logs               recent server logs
#   make backup             pull a consistent copy of the live database to ~/Backups/wingspan
#   make debug [ID=<game>] [AT=<move>]  open that copy locally, read-only, in the owner's seat (at a move)
#   make reports            bug reports from players, newest first (from a fresh backup)

-include .env
HOST := $(DEPLOY_HOST)
DIR := /srv/wingspan
VERSION := $(shell git rev-parse --short HEAD)$(shell git diff --quiet HEAD || echo -dirty)
BACKUPS := $(HOME)/Backups/wingspan
LATEST := $(BACKUPS)/latest.db

.PHONY: setup deploy logs backup debug reports host

host:
	@test -n "$(HOST)" || { echo "Set DEPLOY_HOST in .env (the server's SSH host; see .env.example)"; exit 1; }

setup: host
	ssh $(HOST) 'sudo mkdir -p $(DIR) && sudo chown $$USER: $(DIR) && mkdir -p $(DIR)/data $(DIR)/backups'
	ssh $(HOST) 'test -f $(DIR)/.env' || scp deploy/server.env.example $(HOST):$(DIR)/.env
	scp deploy/backup.sh $(HOST):$(DIR)/backup.sh
	ssh $(HOST) '(crontab -l 2>/dev/null | grep -v $(DIR)/backup.sh; echo "0 4 * * * $(DIR)/backup.sh >> $(DIR)/backups/backup.log 2>&1") | crontab -'

deploy: host
	docker build --platform linux/amd64 --build-arg APP_VERSION=$(VERSION) -t wingspan:latest .
	docker save wingspan:latest | gzip | ssh $(HOST) 'gunzip | docker load'
	scp deploy/compose.yaml $(HOST):$(DIR)/compose.yaml
	ssh $(HOST) 'docker compose -f $(DIR)/compose.yaml up -d && docker image prune -f'
	ssh $(HOST) 'for i in $$(seq 30); do curl -fsS 127.0.0.1:8090/healthz && exit 0; sleep 1; done; docker logs --tail 50 wingspan; exit 1'

logs: host
	ssh $(HOST) 'docker logs --tail 100 wingspan'

# SQLite's backup API inside the container: a plain file copy can miss writes still in the WAL.
backup: host
	mkdir -p $(BACKUPS)
	ssh $(HOST) "docker exec wingspan python -c \"from wingspan.web.store import backup; backup('/data/games.db', '/data/export.db')\""
	scp $(HOST):$(DIR)/data/export.db $(BACKUPS)/games-$(shell date +%Y%m%d-%H%M%S).db
	cp $$(ls -t $(BACKUPS)/games-*.db | head -1) $(LATEST)

debug: backup
	(sleep 3 && open "http://127.0.0.1:8765/$(if $(ID),game.html?g=$(ID)$(if $(AT),@$(AT)))") &
	uv run wingspan --db $(LATEST) --debug --no-browser

reports: backup
	@uv run python -m wingspan.web.store reports $(LATEST)
