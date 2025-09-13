# To run:
#   docker build . -t  authoring-tool 
#   docker run -p 8000:8000 -it --rm authoring-tool 
#   docker run --env-file .env -p 8000:8000 -it --rm authoring-tool

# docker run --name auth-tool-postgres -e POSTGRES_PASSWORD=postgres -d postgres

# -- Frontend dependencies
FROM node:22-bookworm-slim as build-frontend

COPY frontend /app/frontend
WORKDIR /app/frontend
RUN npm ci &&\
 npm exec -- vite build --outDir dist

# -- Backend dependencies

FROM python:3.12-slim-bookworm as backend-deps
ENV PYTHONUNBUFFERED=1
COPY backend/requirements.txt /app/requirements.txt
RUN apt-get update &&\
    apt-get --no-install-recommends install gcc libpq-dev zlib1g-dev libjpeg-dev -y
RUN python -m venv /venv &&\
    /venv/bin/pip install --upgrade pip &&\
    /venv/bin/pip install wheel setuptools gunicorn -r /app/requirements.txt

# -- Final image    

FROM python:3.12-slim-bookworm as final
RUN apt-get update &&\
    apt-get --no-install-recommends install libpq5 zlib1g libjpeg62-turbo gosu -y

COPY --from=backend-deps /venv /venv
COPY backend/ /app
COPY docker-entrypoint.sh /
COPY --from=build-frontend /app/frontend/dist /app/frontend/serve
WORKDIR /app
ENV PYTHONPATH=/app
ENV DJANGO_SETTINGS_MODULE=backend.settings.local

# -- Permissions and entrypoint

ENTRYPOINT [ "/docker-entrypoint.sh" ]
CMD ["/venv/bin/gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8000"]
