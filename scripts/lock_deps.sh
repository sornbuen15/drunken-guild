#!/bin/bash
set -e

echo "Compiling requirements.txt for production..."
pip-compile pyproject.toml -o requirements.txt

echo "Compiling requirements-dev.txt for development and testing..."
pip-compile pyproject.toml --extra dev -o requirements-dev.txt

echo "Lockfiles generated successfully!"
