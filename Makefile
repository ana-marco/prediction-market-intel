PYTHON = ./venv/Scripts/python.exe
CHAINLIT = ./venv/Scripts/chainlit.exe

.PHONY: setup init-db load-data build run test clean help

help:
	@echo "Available targets:"
	@echo "  make setup      Full pipeline: docker + init + load + build"
	@echo "  make init-db    Initialize database schemas"
	@echo "  make load-data  Load all data sources"
	@echo "  make build      Build Neo4j graph + ChromaDB embeddings"
	@echo "  make run        Start Chainlit UI"
	@echo "  make test       Run pytest suite"
	@echo "  make clean      Stop Docker containers"

setup: init-db load-data build
	@echo "Pipeline complete."

init-db:
	docker compose up -d
	$(PYTHON) scripts/init_db.py

load-data:
	$(PYTHON) scripts/load_polymarket.py
	$(PYTHON) scripts/load_guardian.py
	$(PYTHON) scripts/load_govuk.py
	$(PYTHON) scripts/load_fred.py
	$(PYTHON) scripts/load_reddit.py

build:
	$(PYTHON) scripts/build_graph.py
	$(PYTHON) scripts/build_embeddings.py

run:
	$(CHAINLIT) run src/ui/app.py

test:
	PYTHONPATH=. $(PYTHON) -m pytest tests/ -v

clean:
	docker compose down
