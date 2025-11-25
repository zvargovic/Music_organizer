FROM debian:12

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    ESSENTIA_MODELS_DIR=/usr/local/share/essentia/models

RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo git wget curl build-essential cmake pkg-config \
    python3 python3-pip python3-dev python3-venv cython3 \
    swig gfortran liblapack-dev libblas-dev \
    libfftw3-dev libsamplerate-dev libeigen3-dev libyaml-cpp-dev \
    libtag1-dev \
    libchromaprint-dev \
    libfreetype-dev \
    libavcodec-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev libavfilter-dev \
    ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/MTG/essentia /tmp/essentia && \
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
    make install && ldconfig && \
    cd /tmp/essentia/build/src/python && python3 setup.py install && \
    rm -rf /tmp/essentia

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install spotdl

RUN useradd -m appuser
USER appuser
WORKDIR /app

CMD ["bash"]