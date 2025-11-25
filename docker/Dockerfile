# ČISTI MULTI-ARCH DEBIAN BASE IMAGE
FROM debian:12-slim

# Bez interaktivnih dialoga
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONUNBUFFERED=1

# OS paketi (Python, ffmpeg, git, curl...)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        ffmpeg \
        git \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pip upgrade + spotDL
RUN pip3 install --upgrade pip && \
    pip3 install spotdl

# Non-root user i radni direktorij
RUN useradd -m appuser
USER appuser

WORKDIR /app

CMD ["bash"]