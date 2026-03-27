#!/bin/bash

# If DB not in volume yet, copy it there (first run only)
if [ ! -f "/data/moviefinder.db" ]; then
  echo "Copying database to volume..."
  cp /app/data/moviefinder.db /data/moviefinder.db
  echo "Database copied!"
fi

exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
