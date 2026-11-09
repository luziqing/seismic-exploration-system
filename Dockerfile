FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.12 and system dependencies
#   python3.12 / python3.12-venv / python3-pip  — Python runtime
#   libgl1-mesa-glx / libglib2.0-0              — OpenCV (Pillow/matplotlib backend)
#   libsqlite3-0                                — SQLite shared library
#   curl                                        — health check
#   tini                                        — PID 1 signal forwarding
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3-pip \
        libgl1-mesa-glx \
        libglib2.0-0 \
        libsqlite3-0 \
        curl \
        tini && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Make python3.12 the default python
RUN update-alternatives --install /usr/bin/python  python  /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    python -m ensurepip --upgrade

WORKDIR /app

# ── PyTorch with CUDA 12.1 (heaviest layer, rarely changes → cached) ──
RUN pip install --no-cache-dir \
    torch>=2.0.0 \
    torchvision>=0.15.0 \
    --extra-index-url https://download.pytorch.org/whl/cu121

# ── Remaining dependencies ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code (no data/ — that is volume-mounted) ──
COPY index.html .
COPY src/ src/

# Ensure the data directory skeleton exists so Docker can mount over it
RUN mkdir -p data/weights data/db data/uploads data/sgy data/npy \
             data/zarr data/vds data/images/inline \
             data/images/crossline data/images/timeslice

# Bare imports in server.py (e.g. `import sam_service`) need src/ on sys.path
ENV PYTHONPATH=/app/src

# ── Non-root user for security ──
RUN groupadd -r sam3 && useradd -r -g sam3 -d /app -s /sbin/nologin sam3 && \
    chown -R sam3:sam3 /app
USER sam3

ENV SAM3_HOST=0.0.0.0
ENV SAM3_PORT=8000

EXPOSE ${SAM3_PORT}

# tini as PID 1 — forwards SIGTERM to uvicorn for graceful shutdown
ENTRYPOINT ["tini", "--"]

CMD ["python", "src/server.py"]
