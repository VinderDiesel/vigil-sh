.PHONY: help install install-packages test test-packages conformance lint typecheck check demo clean

help:
	@echo "install      安装（含 dev 依赖）"
	@echo "test         单元 + conformance"
	@echo "conformance  仅插件合规测试"
	@echo "lint         ruff"
	@echo "typecheck    mypy(strict)"
	@echo "check        lint + typecheck + test（提交前必跑）"
	@echo "demo         端到端最小样例"
	@echo "clean        清理产物"

install:
	pip install -e ".[dev]"

install-packages:
	pip install -e "packages/vigil-collector-langfuse" -e "packages/vigil-env-docker"

test:
	pytest

test-packages:
	pytest packages/vigil-collector-langfuse
	pytest packages/vigil-env-docker

conformance:
	pytest conformance -m conformance

lint:
	ruff check . && ruff format --check .
	ruff check packages

typecheck:
	mypy

check: lint typecheck test test-packages

demo:
	vigil plugins
	vigil collect examples/minimal-agent/trace.jsonl --out /tmp/vigil-collected.json
	vigil select examples/minimal-agent/trace.jsonl
	vigil run --cases examples/minimal-agent/cases \
		--agent examples/minimal-agent/agent.py \
		--junit /tmp/vigil-junit.xml --json /tmp/vigil-report.json

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find packages -name "*.egg-info" -type d -prune -exec rm -rf {} +
