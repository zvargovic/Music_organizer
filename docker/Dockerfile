FROM mtgupf/essentia:latest

# Tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Python deps
RUN pip install --no-cache-dir \
    torch \
    musicnn \
    librosa \
    numpy \
    scipy \
    pandas \
    matplotlib

WORKDIR /workspace

CMD ["/bin/bash"]