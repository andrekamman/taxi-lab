# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Pin the taxi-seed ref the curated normalize mappings are baked from. They are
# NOT in the wheel -- [tool.hatch.build.targets.wheel] ships only src/ packages --
# so they have to come from the repo. Pin to the release tag once one exists.
ARG TAXI_SEED_REF=main

# sqlcmd: needed for Ola's MaintenanceSolution.sql, which is GO-batch separated
# and can only be run by a client that understands GO.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
      > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends mssql-tools18 \
 && apt-get purge -y gnupg && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/mssql-tools18/bin:${PATH}"

# Pristine mappings. preflight copies them onto the volume on first run and
# never overwrites, so drift amendments survive the container.
RUN mkdir -p /opt/taxi-seed/mappings \
 && for t in yellow green fhv fhvhv; do \
      curl -fsSL -o "/opt/taxi-seed/mappings/$t.yaml" \
        "https://raw.githubusercontent.com/andrekamman/taxi-seed/${TAXI_SEED_REF}/normalize/mappings/$t.yaml"; \
    done

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY seeder/ ./seeder/
COPY k6-loadtest/ ./k6-loadtest/
RUN pip install --no-cache-dir .

# CWD is the data dir: `normalize` resolves mappings from the RELATIVE path
# normalize/mappings/<type>.yaml, so this is load-bearing, not cosmetic.
WORKDIR /data
ENTRYPOINT ["taxi-seeder"]
