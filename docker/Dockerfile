# ČISTI MULTI-ARCH DEBIAN BASE IMAGE
FROM debian:12-slim

# Bez interaktivnih dialoga + dozvoli pipu da dira system packages
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    ESSENTIA_MODELS_DIR=/usr/local/share/essentia/models

# OS paketi (Python, ffmpeg, git, curl...) + build-depovi za Essentiu
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv python3-dev cython3 \
        ffmpeg \
        git \
        curl \
        ca-certificates \
        sqlite3 \
        build-essential \
        cmake \
        pkg-config \
        libfftw3-dev \
        libsamplerate-dev \
        libeigen3-dev \
        libyaml-cpp-dev \
        libtag1-dev \
        libavcodec-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev \
    && rm -rf /var/lib/apt/lists/*

# === ESSENTIA: build iz source-a, full + Python bindings + modeli ===
RUN git clone --depth 1 https://github.com/MTG/essentia.git /tmp/essentia && \
    cd /tmp/essentia && \
    mkdir build && cd build && \
    cmake .. \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHARED=ON \
        -DBUILD_PYTHON_BINDINGS=ON \
        -DESSENTIA_BUILD_EXAMPLES=OFF \
        -DESSENTIA_BUILD_TESTS=OFF \
        -DESSENTIA_BUILD_BENCHMARKS=OFF \
        -DESSENTIA_BUILD_VAMP_PLUGINS=OFF && \
    make -j"$(nproc)" && \
    make install && \
    ldconfig && \
    # instaliraj Python bindinge
    cd /tmp/essentia/build/src/python && \
    python3 setup.py install && \
    # očisti source da ne deblja image
    rm -rf /tmp/essentia

# Wrapper za binarku koju želiš: essentia_streaming_extractor_music_svm
# (poziva osnovni streaming_extractor_music, s instaliranim modelima)
RUN printf '#!/bin/sh\nexec streaming_extractor_music "$@"\n' > /usr/local/bin/essentia_streaming_extractor_music_svm && \
    chmod +x /usr/local/bin/essentia_streaming_extractor_music_svm

# Pip upgrade + spotDL (sad radi jer je PIP_BREAK_SYSTEM_PACKAGES=1)
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install spotdl

# Non-root user i radni direktorij
RUN useradd -m appuser
USER appuser

WORKDIR /app

CMD ["bash"]