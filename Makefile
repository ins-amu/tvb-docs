# TVB Documentation & JupyterLite Build System
# Self-documenting Makefile: run `make help` or `make` for target descriptions.

.DEFAULT_GOAL := help

export PATH := $(HOME)/.local/bin:/opt/homebrew/bin:$(PATH)
LITE_ENV ?= $(shell test -f environment.ci.yml && echo environment.ci.yml || echo environment.yml)
JUPYTER_CMD ?= $(shell test -x $(HOME)/.micromamba/envs/build-tvbl/bin/jupyter && echo "$(HOME)/.micromamba/envs/build-tvbl/bin/jupyter" || echo "jupyter")
TVBL_TEST_DIR ?= $(shell test -d /Users/duke/src/tvbl/content/tvbl && echo "/Users/duke/src/tvbl/content/tvbl" || echo "content/_code")

.PHONY: help setup refs docs test check lite-setup lite all serve clean

help: ## Show this help message
	@echo "TVB Docs & JupyterLite Build Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""

setup: ## Create .venv and install pinned dependencies from uv.lock
	uv venv
	uv pip sync requirements/uv.lock

refs: ## Validate BibTeX citations against Crossref API
	python3 tools/check_refs.py content/references.bib

docs: ## Build MyST HTML docs with execution and stage JupyterLite contents
	uv run myst build --execute --html
	uv run python tools/stage_lite.py

test: ## Run unit tests and reference checks
	PYTHONPATH=content/_code uv run --with pytest pytest -q $(TVBL_TEST_DIR)
	python3 tools/check_refs.py content/references.bib

check: refs docs ## Run the exact checks CI runs on PRs (refs + docs)

lite-setup: ## Create ~/.micromamba/envs/build-tvbl from build-environment.yml
	micromamba create -y -p $(HOME)/.micromamba/envs/build-tvbl -f build-environment.yml

lite: ## Build JupyterLite site into _build/html/lite and apply runtime patches
	uv run python tools/stage_lite.py
	$(JUPYTER_CMD) lite build --contents _build/lite_contents --output-dir _build/html/lite --XeusAddon.environment_file=$(LITE_ENV)
	@if [ -d "_build/html/lite/extensions/catppuccin_jupyterlab/themes/catppuccin_jupyterlab" ]; then \
		mkdir -p _build/html/lite/build/themes; \
		cp -rv _build/html/lite/extensions/catppuccin_jupyterlab/themes/catppuccin_jupyterlab _build/html/lite/build/themes/; \
	fi
	cp .nojekyll _build/html/.nojekyll
	python3 tools/patch_lite_runtime.py _build/html/lite

all: docs lite ## Build complete unified static site (_build/html with MyST docs and JupyterLite)

serve: ## Serve unified static site locally at http://localhost:8000
	python3 -m http.server 8000 --directory _build/html

clean: ## Remove build artifacts and temporary databases
	rm -rf _build/site _build/html _build/execute _build/lite_contents .jupyterlite.doit.db cockle_wasm_env
