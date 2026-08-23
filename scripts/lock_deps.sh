#!/bin/bash
set -e

# `uv`, not `pip-compile`. Each generated file records its own generator in its
# header, and this script used to run a different one: requirements-dev.txt says
# `uv pip compile`, while this script compiled it with pip-tools. Two generators
# for one artefact means whoever regenerates decides what lands in git, which is
# the same failure DG-280 found in the INDEX.md generators. DG-271.
#
# There is no production requirements.txt line any more. Nothing read that
# file and it drifted 113 lines from pyproject before anyone noticed, so
# DG-281 retired it to _not_used/requirements/. Reproducible installs come
# from uv.lock, exported on demand -- see that directory's RETIRED.md.

echo "Compiling requirements-dev.txt for development and testing..."
uv pip compile pyproject.toml --extra dev -o requirements-dev.txt

echo "Lockfiles generated successfully!"
