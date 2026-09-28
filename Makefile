SHELL := /bin/bash

.DEFAULT_GOAL := help
.NOTPARALLEL: pilot smoke

# Resolve paths from this Makefile, not from the caller's shell and not from a
# global shell profile. This keeps `git clone && cd repo && make <target>`
# portable across the development and production checkouts.
REPO_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PROD ?= 0
PROD_ENV_FILE ?= /etc/patra-darpan/retrieval.env

ifneq ($(filter 1 true yes,$(strip $(PROD))),)
ENV_FILE ?= $(PROD_ENV_FILE)
else
ENV_FILE ?= $(REPO_DIR)/.env
endif

COMPOSE_BASE := docker compose --env-file "$(ENV_FILE)" \
	-f "$(REPO_DIR)/docker-compose.retrieval.yml"

ifneq ($(filter 1 true yes,$(strip $(PROD))),)
COMPOSE := $(COMPOSE_BASE) -f "$(REPO_DIR)/docker-compose.retrieval.prod.yml"
MODE := production
else
COMPOSE := $(COMPOSE_BASE)
MODE := development
endif

.PHONY: help prod-env check config test build qdrant wait-qdrant index inspect mcp up \
	backend-smoke mcp-smoke smoke pilot https logs down

help:
	@printf '%s\n' \
		"Retrieval commands ($(MODE))" \
		"  make help                          Show commands and environment defaults" \
		"  make PROD=1 prod-env               Create the private production env file once" \
		"  make check                         Validate env, Compose, and whitespace" \
		"  make test                          Run Python unit tests (development)" \
		"  make build                         Build retrieval images" \
		"  make qdrant                        Start persistent Qdrant" \
		"  make wait-qdrant                   Start Qdrant and wait until ready (used by index)" \
		"  make index                         Build chunks, entities, vectors, release" \
		"  make inspect                       Inspect the active release" \
		"  make mcp                           Start the MCP runtime" \
		"  make backend-smoke                 Optional backend check (included in smoke)" \
		"  make mcp-smoke                     Optional MCP check (included in smoke)" \
		"  make smoke                         Run both checks against the active release" \
		"  make pilot                         Full flow; includes the index build" \
		"  make https                         Start the local HTTPS adapter (development)" \
		"  make logs                          Follow retrieval logs" \
		"  make down                          Stop the retrieval Compose project" \
		"" \
		"Development env: $(REPO_DIR)/.env" \
		"Production env:  $(PROD_ENV_FILE) (override with ENV_FILE=...)" \
		"Production run:  make PROD=1 pilot"

prod-env:
	@if [ "$(MODE)" != "production" ]; then \
		echo "Run this target as: make PROD=1 prod-env" >&2; exit 2; \
	fi
	@set -eu; \
	  destination="$(ENV_FILE)"; \
	  if [ -e "$$destination" ]; then \
	    echo "Preserving existing env file: $$destination"; \
	  else \
	    sudo mkdir -p "$$(dirname "$$destination")"; \
	    sudo install -o "$$(id -un)" -g "$$(id -gn)" -m 600 \
	      "$(REPO_DIR)/retrieval.env.prod.example" "$$destination"; \
	    echo "Created $$destination from retrieval.env.prod.example"; \
	  fi; \
	  echo "Set MCP_BEARER_TOKEN in $$destination before starting services."; \
	  echo "Then validate with: make PROD=1 check"

config:
	@test -f "$(ENV_FILE)" || { \
		echo "Missing env file: $(ENV_FILE)" >&2; \
		if [ "$(MODE)" = "production" ]; then \
		  echo "Create it with: make PROD=1 prod-env" >&2; \
		else \
		  echo "Copy retrieval.env.example to .env for development." >&2; \
		fi; \
		exit 2; \
	}
	@if [ "$(MODE)" = "production" ]; then \
	  if ! grep -Eq '^MCP_BEARER_TOKEN=.+$$' "$(ENV_FILE)" || \
	     grep -Fqx 'MCP_BEARER_TOKEN=replace-this-before-starting' "$(ENV_FILE)"; then \
	    echo "Set a non-placeholder MCP_BEARER_TOKEN in $(ENV_FILE)." >&2; exit 2; \
	  fi; \
	fi
	@$(COMPOSE) --profile build --profile runtime config --quiet

check: config
	@git -C "$(REPO_DIR)" diff --check
	@echo "Compose and source checks passed ($(MODE))."

test:
	@cd "$(REPO_DIR)" && uv run python -m unittest discover -s tests -q

build: check
	$(COMPOSE) --profile build build retrieval-builder retrieval-mcp

qdrant: check
	$(COMPOSE) up -d qdrant

# Wait through the builder image so this works with both the development
# service URL and the production overlay's private qdrant service URL.
wait-qdrant: build qdrant
	$(COMPOSE) --profile build run --rm --no-deps retrieval-builder \
		python scripts/wait_for_qdrant.py

index: wait-qdrant
	$(COMPOSE) --profile build run --rm retrieval-builder

inspect: check
	$(COMPOSE) --profile runtime run --rm --no-deps retrieval-mcp \
		python -c 'import json; from pathlib import Path; p=Path("/var/lib/retrieval/releases/active-release.json"); print(json.dumps(json.loads(p.read_text()), ensure_ascii=False, indent=2))'

mcp: qdrant inspect
	$(COMPOSE) --profile runtime up -d retrieval-mcp

up: mcp

backend-smoke: mcp
	$(COMPOSE) --profile runtime run --rm --no-deps retrieval-mcp \
		python scripts/smoke_retrieval.py --require-backends

mcp-smoke: mcp
	$(COMPOSE) --profile runtime run --rm --no-deps retrieval-mcp \
		python scripts/mcp_smoke.py --url http://retrieval-mcp:8787/mcp

smoke: backend-smoke mcp-smoke
	@echo "Backend and MCP smoke checks passed."

pilot: check build index inspect smoke
	@echo "Retrieval pilot flow completed ($(MODE))."

https: mcp
	$(COMPOSE) --profile runtime --profile https up -d retrieval-https

logs:
	$(COMPOSE) --profile runtime --profile https logs -f --tail=100

down:
	$(COMPOSE) --profile runtime --profile https down
