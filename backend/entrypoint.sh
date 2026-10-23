#!/bin/sh
set -e

# Bring the schema up to date before the API starts. If this fails, the container exits
# instead of serving against an old schema.
alembic upgrade head

exec "$@"
