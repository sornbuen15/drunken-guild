#!/bin/bash
set -e

# `uv`, not `pip-compile`. Each generated file records its own generator in its
# header, and this script used to run a different one: requirements-dev.txt says
# `uv pip compile`, while this script compiled it with pip-tools. Two generators
# for one artefact means whoever regenerates decides what lands in git, which is
# the same failure DG-280 found in the INDEX.md generators. DG-271.

echo "Compiling requirements.txt for production..."
uv pip compile pyproject.toml -o requirements.txt

echo "Compiling requirements-dev.txt for development and testing..."
uv pip compile pyproject.toml --extra dev -o requirements-dev.txt

echo "Lockfiles generated successfully!"
