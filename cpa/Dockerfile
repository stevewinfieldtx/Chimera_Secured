FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/wintechpartners/chimera-secured"
LABEL org.opencontainers.image.description="Chimera Secured CPA — Communication Personality Analyzer"

# System deps for scipy/scikit-learn/xgboost wheel builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY static/ ./static/

# Default data directory
RUN mkdir -p /app/cpa_data/artifacts

ENV PYTHONUNBUFFERED=1
ENV CPA_DATA_DIR=/app/cpa_data
ENV CPA_ARTIFACTS_DIR=/app/cpa_data/artifacts

EXPOSE 8000

# Run from the src directory so imports work
WORKDIR /app/src
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
