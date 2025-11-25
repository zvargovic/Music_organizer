# ČISTI MULTI-ARCH DEBIAN BASE IMAGE
FROM debian:12-slim

# Bez interaktivnih dialoga + dozvoli pipu da dira system packages
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# OS paketi (Python, ffmpeg, git, curl...)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        ffmpeg \
        git \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pip upgrade + spotDL (sad radi jer je PIP_BREAK_SYSTEM_PACKAGES=1)
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install spotdl

# Non-root user i radni direktorij
RUN useradd -m appuser
USER appuser

WORKDIR /app

CMD ["bash"]