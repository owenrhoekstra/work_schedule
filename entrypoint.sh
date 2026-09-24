#!/bin/sh
set -e

echo "Building Tailwind CSS..."
python manage.py tailwind build

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Starting: $@"
exec "$@"