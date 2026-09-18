# ApplyFirst V2 SaaS — Fly.io image.
# Runs the web server AND the poll worker in one machine (see entrypoint.sh) so both
# processes share the SQLite DB on the mounted /data volume.
#
# Python 3.12 (not 3.14) on purpose: it has guaranteed manylinux wheels for every dep
# (cryptography, pydantic-core, selectolax, fpdf2), so the image build never needs a
# compiler. The app is 3.10+ safe — bump this to 3.14 later if you want to match local dev.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

# CA certs for outbound HTTPS: Google OAuth, the Gmail API, Gemini, and onlinejobs.ph.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App code + the container entrypoint.
COPY applyfirst ./applyfirst
COPY entrypoint.sh ./entrypoint.sh
# Strip any CR (a CRLF shebang makes the kernel fail to exec /bin/sh) + make executable.
RUN sed -i 's/\r$//' ./entrypoint.sh && chmod +x ./entrypoint.sh

# uvicorn listens here; fly.toml maps the public 443 -> 8080.
EXPOSE 8080

CMD ["./entrypoint.sh"]
