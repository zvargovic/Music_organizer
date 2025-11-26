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
# 1) OS + build alati + Essentia ovisnosti v1
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
        python-is-python3 \
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
#    PEP 668 fix: dopuštamo pip-u da dira system env u containeru
# ---------------------------------------------------------------------
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Moderni znanstveni stack + librosa
RUN pip install --no-cache-dir \
        numpy \
        scipy \
        pandas \
        matplotlib \
        librosa

# Torch CPU iz službenog repoa
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu torch

# musicnn bez provjere njegovih zastarjelih dependencija (numpy<1.17)
RUN pip install --no-cache-dir --no-deps musicnn

# ---------------------------------------------------------------------
# 3) Essentia build (full, s Python bindingima)
# ---------------------------------------------------------------------
WORKDIR /opt

RUN git clone --depth 1 https://github.com/MTG/essentia.git

WORKDIR /opt/essentia

RUN ./waf configure \
        --mode=release \
        --with-python \
        --with-examples \
        --with-vamp \
        --with-avcodec=no \
        --with-avformat=no \
        --with-swresample=no \
        --with-avdevice=no \
        --with-videotools=no \
    && ./waf \
    && ./waf install \
    && ldconfig

# ---------------------------------------------------------------------
# 4) Self-test – Essentia + musicnn + torch
# ---------------------------------------------------------------------
RUN python3 -c "import essentia, musicnn, torch; print('Self-test OK')"

# ---------------------------------------------------------------------
# 5) Workdir
# ---------------------------------------------------------------------
WORKDIR /workspace

CMD ["/bin/bash"]