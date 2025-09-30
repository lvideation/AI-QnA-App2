#!/bin/bash
set -e

PROJECT_ROOT="/Users/venky/AI-QnA-App2"

cd "$PROJECT_ROOT"

echo ">>> Cleaning up old structure in $PROJECT_ROOT"

# 1. Remove venv
if [ -d "venv" ]; then
  echo "Removing existing venv..."
  rm -rf venv
fi

# 2. Move scripts into tools/
if [ -d "scripts" ]; then
  echo "Moving scripts/ to tools/..."
  mv scripts tools
fi

# 3. Create new scaffold
echo "Creating new app scaffold..."
mkdir -p app/{db,llm,ui,session,admin}
mkdir -p tests

# 4. Create template files if not exist
[ -f ".env.example" ] || echo "# copy to .env and fill in per machine" > .env.example
[ -f "README.md" ] || echo "# AI-QnA-App2" > README.md

echo ">>> Done. New structure is ready:"
