# =====================================================================
# Z-MUSIC-ORGANIZER – Essentia + musicnn + Torch (MTG base image)
# =====================================================================

FROM ghcr.io/mtg/essentia:ubuntu20.04-v2.1_beta5

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1

# 1) System tools + pip
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    ffmpeg \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 2) Python paketi: Torch CPU + musicnn + znanstveni stack
RUN pip3 install --no-cache-dir \
    torch \
    musicnn \
    librosa \
    numpy \
    scipy \
    pandas \
    matplotlib

# 3) Radni direktorij
WORKDIR /workspace

CMD ["/bin/bash"]