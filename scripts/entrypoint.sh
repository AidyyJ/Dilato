#!/bin/bash
set -e

# Run migrations before starting the application
/scripts/run_migrations.sh

# Start the application
echo "Starting application..."
exec "$@"
