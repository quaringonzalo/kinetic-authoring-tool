#!/usr/bin/env bash
set -e

#create a user and group in the container to access the bind mount from the host
if ! getent group user > /dev/null 2>&1; then
    groupadd -g ${PGID} user
fi

if ! getent passwd user > /dev/null 2>&1; then
    useradd -u ${PUID} -g user user
fi

# Create the application directory
# mkdir -p /app/frontend/serve/root
#chown -R user:user /app/frontend/serve/root

#fix ownership of the bind mount
mkdir -p /app/backend/files
chown -R user:user /app/backend/files

# allow manage.py collectstatic to write to /app/backend/staticfiles
mkdir -p /app/backend/staticfiles
chown -R user:user /app/backend/staticfiles

gosu user /venv/bin/python manage.py collectstatic --noinput
gosu user /venv/bin/python manage.py migrate

# Execute the main command
exec gosu user "$@"