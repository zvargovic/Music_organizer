# ============================================================================
# Z-MUSIC-ORGANIZER — Conda-based image (Essentia + musicnn + Torch CPU)
# Debian + Miniconda + Essentia (prebuilt) + musicnn
# ============================================================================

FROM continuumio/miniconda3:4.12.0

ENV DEBIAN_FRONTEND=noninteractive \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1

# ---------------------------------------------------------------------------
# 1) System tools
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
        curl \
        wget \
        build-essential \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 2) Conda environment + Essentia (+ scientific stack)
# ---------------------------------------------------------------------------
RUN conda install -y -c conda-forge \
        python=3.11 \
        essentia \
        numpy \
        scipy \
        pandas \
        matplotlib \
        librosa

# ---------------------------------------------------------------------------
# 3) PIP packages (Torch CPU + musicnn)
# ---------------------------------------------------------------------------
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch \
    && pip install --no-cache-dir \
        musicnn

# ---------------------------------------------------------------------------
# 4) Working directory
# ---------------------------------------------------------------------------
WORKDIR /workspace

CMD ["/bin/bash"]