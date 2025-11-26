# =====================================================================
# Z-MUSIC-ORGANIZER - FULL DEV IMAGE (DEBIAN CI VARIJANTA)
# Debian 12 + Essentia (full, with Python) + musicnn + Torch CPU
# =====================================================================

FROM debian:12

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

# ---------------------------------------------------------------------
# 1) OS + build alati + Essentia ovisnosti
# ---------------------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        git \
        wget \
        curl \
        pkg-config \
        # python
        python3 \
        python3-dev \
        python3-pip \
        python3-setuptools \
        python3-numpy \
        python3-yaml \
        python3-six \
        # math / lapack / blas
        liblapack-dev \
        libblas-dev \
        gfortran \
        # Essentia deps
        libeigen3-dev \
        libyaml-dev \
        libfftw3-dev \
        libsamplerate0-dev \
        libavcodec-dev \
        libavformat-dev \
        libavutil-dev \
        libswresample-dev \
        libswscale-dev \
        libavdevice-dev \
        libsndfile1-dev \
        libchromaprint-dev \
        libtag1-dev \
        libboost-all-dev \
        swig \
        vamp-plugin-sdk \
        ladspa-sdk \
        libssl-dev \
        libffi-dev \
        zlib1g-dev \
        ffmpeg \
        sqlite3 \
        libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------
# 2) Python paketi – znanstveni stack + Torch CPU + musicnn
# ---------------------------------------------------------------------
RUN python3 -m pip install --upgrade pip

RUN pip install --no-cache-dir \
        numpy \
        scipy \
        pandas \
        matplotlib \
        librosa \
    && pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir \
        musicnn

# ---------------------------------------------------------------------
# 3) Essentia build (full, s Python bindingima)
# ---------------------------------------------------------------------
WORKDIR /opt

RUN git clone --depth 1 https://github.com/MTG/essentia.git

WORKDIR /opt/essentia

RUN ./waf configure \
        --mode=release \
        --with-python \
        --with-cpptests \
        --with-examples \
        --with-vamp \
    && ./waf \
    && ./waf install \
    && ldconfig

# ---------------------------------------------------------------------
# 4) Self-test – Essentia + musicnn + torch
# ---------------------------------------------------------------------
RUN python3 - << 'EOF'
import sys
print("=== PYTHON VERSION ===")
print(sys.version)

print("=== TEST: essentia ===")
import essentia
from essentia import standard
print("Essentia module:", essentia.__file__)
print("Essentia version:", getattr(essentia, "__version__", "N/A"))
loader = standard.MonoLoader(filename=None)
print("Essentia standard OK.")

print("=== TEST: musicnn ===")
import musicnn
from musicnn.tagger import top_tags
print("musicnn module:", musicnn.__file__)
print("musicnn OK (import).")

print("=== Torch info ===")
import torch
print("Torch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
EOF

# ---------------------------------------------------------------------
# 5) Workdir
# ---------------------------------------------------------------------
WORKDIR /workspace

CMD ["/bin/bash"]