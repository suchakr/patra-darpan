SHELL := /bin/bash

.DEFAULT_GOAL := help
.NOTPARALLEL: index pilot smoke up refresh-release

# Resolve paths from this Makefile, not from the caller's shell and not from a
# global shell profile. This keeps `git clone && cd repo && make <target>`
# portable across the development and production checkouts.
REPO_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PROD_ENV_FILE ?= /etc/patra-darpan/retrieval.env

ifneq ($(strip $(ENV_FILE)),)
ENV_FILE := $(abspath $(ENV_FILE))
ifneq ($(filter $(abspath $(PROD_ENV_FILE)),$(ENV_FILE)),)
MODE := production
else
MODE := development
endif
else ifneq ($(wildcard $(PROD_ENV_FILE)),)
ENV_FILE := $(abspath $(PROD_ENV_FILE))
MODE := production
else
ENV_FILE := $(REPO_DIR)/.env
MODE := development
endif

COMPOSE_BASE := docker compose --env-file "$(ENV_FILE)" \
	-f "$(REPO_DIR)/docker-compose.retrieval.yml"

ifneq ($(filter production,$(MODE)),)
COMPOSE := $(COMPOSE_BASE) -f "$(REPO_DIR)/docker-compose.retrieval.prod.yml"
else
COMPOSE := $(COMPOSE_BASE)
endif

.PHONY: help prod-env check config test build runtime-build catalog qdrant wait-qdrant index inspect mcp up \
	refresh-release backend-smoke mcp-smoke search-smoke smoke pilot oauth-config edge edge-smoke https logs down

ifeq ($(MODE),development)
EDGE_UP_SERVICES := retrieval-mcp-oauth retrieval-https
EDGE_SMOKE_ARGS := --base-url "$${MCP_EDGE_URL:-https://retrieval-https:8443}" --allow-insecure
else
EDGE_UP_SERVICES := retrieval-mcp-oauth
# The OAuth container already receives the issuer from the selected env file.
EDGE_SMOKE_ARGS := --base-url "$${MCP_EDGE_URL:-$${MCP_OAUTH_ISSUER_URL:?Set MCP_OAUTH_ISSUER_URL}}"
endif

help:
	@printf '%s\n' \
		"Retrieval commands ($(MODE))" \
		"  make help                          Show commands and environment defaults" \
		"  make PROD=1 prod-env               Create the private production env file once" \
		"  make check                         Validate env, Compose, and whitespace" \
		"  make test                          Run Python unit tests (development)" \
		"  make build                         Build retrieval images" \
		"  make runtime-build                 Build only the MCP runtime image" \
		"  make up                            Build/start MCP and configured OAuth/HTTPS; reuse indexes" \
		"  make catalog                       Build/refresh the canonical SQLite catalog" \
		"  make qdrant                        Start persistent Qdrant" \
		"  make wait-qdrant                   Start Qdrant and wait until ready (used by index)" \
		"  make index                         Build chunks, entities, vectors, release" \
		"  make refresh-release               Refresh provenance/release; reuse verified vectors" \
		"  make inspect                       Inspect the active release" \
		"  make mcp                           Start the MCP runtime" \
		"  make backend-smoke                 Optional backend check (included in smoke)" \
		"  make mcp-smoke                     Optional MCP check (included in smoke)" \
		"  make search-smoke                  Check search expansion, filenames, guide and passage paging" \
		"  make smoke                         Run both checks against the active release" \
		"  make pilot                         Full flow; includes the index build" \
		"  make oauth-config                  Validate OAuth provider and allowlist settings" \
		"  make edge                          Start the HTTPS/OAuth edge" \
		"  make edge-smoke                    Check OAuth discovery, routes, and allowlist" \
		"  make https                          Compatibility alias for edge" \
		"  make logs                          Follow retrieval logs" \
		"  make down                          Stop the retrieval Compose project" \
		"" \
		"Development env: $(REPO_DIR)/.env" \
		"Production env:  $(PROD_ENV_FILE) (override with ENV_FILE=...)" \
		"Selected env:     $(ENV_FILE)" \
		"Production setup: make PROD=1 prod-env"

prod-env:
	@if ! echo "$(PROD)" | grep -Eiq '^(1|true|yes)$$'; then \
		echo "Run this target as: make PROD=1 prod-env" >&2; exit 2; \
	fi
	@set -eu; \
	  destination="$(PROD_ENV_FILE)"; \
	  if [ -e "$$destination" ]; then \
	    echo "Preserving existing env file: $$destination"; \
	  else \
	    sudo mkdir -p "$$(dirname "$$destination")"; \
	    sudo install -o "$$(id -un)" -g "$$(id -gn)" -m 600 \
	      "$(REPO_DIR)/retrieval.env.prod.example" "$$destination"; \
	    echo "Created $$destination from retrieval.env.prod.example"; \
	  fi; \
    echo "Set MCP_BEARER_TOKEN, OAuth client values, and the allowlist path in $$destination before starting services."; \
	  echo "Then validate with: make check"

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
	@$(COMPOSE) --profile build --profile runtime --profile oauth config --quiet

check: config
	@git -C "$(REPO_DIR)" diff --check
	@echo "Compose and source checks passed ($(MODE))."

test:
	@cd "$(REPO_DIR)" && uv run --with 'mcp==1.30.0' --with httpx python -m unittest discover -s tests -q

build: check
	$(COMPOSE) --profile build build retrieval-builder retrieval-mcp

runtime-build: check
	$(COMPOSE) --profile runtime build retrieval-mcp

# The catalog source tree stays read-only in the container. Mount only the
# canonical catalog directory as writable so the atomic file replacement can
# complete without granting write access to the checkout.
catalog: build
	@set -eu; \
	  catalog_file="$$($(COMPOSE) --profile build config --format json | \
	    python3 -c 'import json,sys; s=json.load(sys.stdin)["services"]; t="/var/lib/patra-darpan/spasta-corpus.sqlite"; print(next(v["source"] for v in s["retrieval-builder"]["volumes"] if v.get("target")==t and v.get("type")=="bind"))')"; \
	  case "$$catalog_file" in */.build~/spasta-corpus.sqlite) ;; \
	    *) echo "RETRIEVAL_CANONICAL_CATALOG must end in /.build~/spasta-corpus.sqlite: $$catalog_file" >&2; exit 2 ;; \
	  esac; \
	  catalog_root="$$(dirname "$$catalog_file")"; \
	  mkdir -p "$$catalog_root"; \
	  echo "Building canonical catalog at $$catalog_file"; \
	  $(COMPOSE) --profile build run --rm --no-deps \
	    --volume "$$catalog_root:/data/patra-darpan/.build~:rw" \
	    retrieval-catalog-builder; \
	  test -f "$$catalog_file" || { echo "Catalog build did not create $$catalog_file" >&2; exit 1; }; \
	  echo "Canonical catalog ready: $$catalog_file"

qdrant: check
	$(COMPOSE) up -d qdrant

# Wait through the builder image so this works with both the development
# service URL and the production overlay's private qdrant service URL.
wait-qdrant: build qdrant
	$(COMPOSE) --profile build run --rm --no-deps retrieval-builder \
		python scripts/wait_for_qdrant.py

index: catalog wait-qdrant
	$(COMPOSE) --profile build run --rm retrieval-builder

refresh-release: check build wait-qdrant
	$(COMPOSE) --profile build run --rm retrieval-builder \
		python scripts/refresh_retrieval_release.py --activate

inspect: check
	$(COMPOSE) --profile runtime run --rm --no-deps retrieval-mcp \
		python -c 'import json; from pathlib import Path; p=Path("/var/lib/retrieval/releases/active-release.json"); print(json.dumps(json.loads(p.read_text()), ensure_ascii=False, indent=2))'

mcp: qdrant inspect
	$(COMPOSE) --profile runtime up -d retrieval-mcp

# Runtime update/start path: never reaches catalog, builder or index targets.
# Both MCP processes use the freshly built runtime image. Production TLS is
# still owned by Sanchaya-Zoekt; the development edge is part of this project.
up: runtime-build edge

backend-smoke: mcp
	$(COMPOSE) --profile runtime run --rm --no-deps retrieval-mcp \
		python scripts/smoke_retrieval.py --require-backends

mcp-smoke: mcp
	$(COMPOSE) --profile runtime run --rm --no-deps retrieval-mcp \
		python scripts/mcp_smoke.py --url http://retrieval-mcp:8787/mcp

search-smoke: mcp
	$(COMPOSE) --profile runtime run --rm --no-deps retrieval-mcp \
		python scripts/mcp_smoke.py --url http://retrieval-mcp:8787/mcp --search-features

smoke: backend-smoke mcp-smoke
	@echo "Backend and MCP smoke checks passed."

oauth-config: check
	@set -eu; \
	  for name in MCP_OAUTH_ISSUER_URL MCP_OAUTH_RESOURCE_URL MCP_OAUTH_REDIRECT_URI \
	    MCP_OAUTH_GOOGLE_CLIENT_ID MCP_OAUTH_GOOGLE_CLIENT_SECRET \
	    MCP_OAUTH_ALLOWLIST_FILE RETRIEVAL_AUTH_STATE_ROOT; do \
	    value="$$(grep -E "^$${name}=" "$(ENV_FILE)" | tail -1 | cut -d= -f2-)"; \
	    case "$$value" in ""|replace-*) echo "Set $$name in $(ENV_FILE)" >&2; exit 2;; esac; \
	  done; \
	  $(COMPOSE) --profile runtime --profile oauth run --rm --no-deps \
	    --entrypoint python retrieval-mcp-oauth \
	    -c 'from pathlib import Path; import os, tempfile; a=Path("/etc/retrieval-auth/allowlist.txt"); s=Path("/var/lib/retrieval/auth"); a.read_text(encoding="utf-8"); assert s.is_dir(), f"OAuth state directory is not mounted: {s}"; fd,name=tempfile.mkstemp(prefix=".oauth-config-", dir=s); os.close(fd); Path(name).unlink(); print("OAuth bind mounts passed (container)")'

edge: mcp oauth-config
	$(COMPOSE) --profile runtime --profile oauth --profile https up -d $(EDGE_UP_SERVICES)

edge-smoke: edge
	$(COMPOSE) --profile runtime --profile oauth --profile https run --rm --no-deps \
		--env "MCP_EDGE_URL=$${MCP_EDGE_URL:-}" --entrypoint sh retrieval-mcp-oauth \
		-c 'exec python scripts/oauth_smoke.py $(EDGE_SMOKE_ARGS)'

pilot: check build index inspect smoke
	@echo "Retrieval pilot flow completed ($(MODE))."

https: edge

logs:
	$(COMPOSE) --profile runtime --profile oauth --profile https logs -f --tail=100

down:
	$(COMPOSE) --profile runtime --profile oauth --profile https down
