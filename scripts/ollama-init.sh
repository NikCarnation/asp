#!/bin/sh
set -e

ollama serve &
SERVER_PID=$!

echo "Waiting for Ollama server..."
until ollama list >/dev/null 2>&1; do
  sleep 1
done
echo "Ollama server is ready."

for model in "$@"; do
  echo "Pulling model: $model"
  ollama pull "$model"
done

echo "Pulling embedding model: nomic-embed-text"
ollama pull nomic-embed-text

echo "All models ready. Server running."
wait "$SERVER_PID"
