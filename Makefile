.PHONY: install
install: ## Install the virtual environment, build C extension, and install pre-commit hooks
	@uv sync
	@uv pip install -e .
	@uv run python -m pre_commit install

.PHONY: check
check: ## Run code quality tools
	@uv lock --locked
	@uv run pre-commit run -a
	@uv run mypy

.PHONY: test
test: ## Run the test suite with coverage
	@uv run python -m pytest tests --cov --cov-config=pyproject.toml --cov-report=xml

.PHONY: build
build: clean ## Build sdist and wheel
	@uv build

.PHONY: clean
clean: ## Remove build artifacts
	@rm -rf dist/ build/ *.egg-info quickjs.egg-info quickjs_ng.egg-info wheelhouse/
	@rm -f .coverage coverage.xml
	@find . -name '*.so' -not -path './.venv/*' -delete
	@find . -name '*.o' -not -path './.venv/*' -delete

.PHONY: publish
publish: ## Publish to PyPI
	@uv publish

.PHONY: build-and-publish
build-and-publish: build publish ## Build and publish

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
