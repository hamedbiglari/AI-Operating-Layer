FROM python:3.12-slim

# The image is a deployment artefact, so it starts in production mode: the service refuses to boot while
# SECRET_KEY or the database password still hold development defaults (security audit SEC-09). Override
# APP_ENV only for local development.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    APP_DEBUG=false \
    AIOL_SOURCE_STORE=/var/lib/aiol/sources

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as an unprivileged user (SEC-10): a compromise of a document parser must not be root in the container.
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin aiol \
    && mkdir -p /var/lib/aiol/sources \
    && chown -R aiol:aiol /var/lib/aiol \
    && chmod 0700 /var/lib/aiol/sources
USER aiol

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
