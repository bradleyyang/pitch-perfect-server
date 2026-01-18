# Makefile for FastAPI app

# Use the virtual environment's python if needed
VENV := .venv/bin/activate

# Default port and host
HOST := 127.0.0.1
PORT := 8000

# Run the FastAPI server with reload
run:
	@echo "Starting FastAPI server on http://$(HOST):$(PORT)..."
	uvicorn app.main:app --reload --host $(HOST) --port $(PORT)

# Optional: run in virtual environment (Linux/macOS)
run-venv:
	@echo "Activating venv and starting server..."
	. $(VENV) && uvicorn app.main:app --reload --host $(HOST) --port $(PORT)

# Stop the server (just for info, can't forcibly kill)
stop:
	@echo "Use Ctrl+C to stop the server."
