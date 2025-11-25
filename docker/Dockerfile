# MULTI-ARCH DEBIAN BASE IMAGE
FROM debian:12-slim

# OBRIŠI SVE IZVORE KOJE DEBIAN SLIM DONOSI
RUN rm -f /etc/apt/sources.list && \
    rm -f /etc/apt/sources.list.d/*

# STAVI CLOUDLFARE MIRROR U SVA 3 KANALA
RUN echo "deb http://mirror.cloudflare.com/debian bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb http://mirror.cloudflare.com/debian bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb http://mirror.cloudflare.com/debian-security bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONUNBUFFERED=1

# --- BITNO: --fix-missing ZA ARM64 ---
RUN apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        ffmpeg \
        git \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip && \
    pip3 install spotdl

RUN useradd -m appuser
USER appuser

WORKDIR /app

CMD ["bash"]