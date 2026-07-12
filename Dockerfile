# --- Stage 1: Build the React frontend ---
FROM node:22-alpine AS frontend-build

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Empty API base => the built app calls the same origin, which FastAPI serves.
ENV VITE_API_URL=""
RUN npm run build


# --- Stage 2: FastAPI backend serving the API + the built UI ---
FROM python:3.11-slim AS app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user. Required by Hugging Face Spaces (which launches the
# container as uid 1000) and good practice everywhere else.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Backend source
COPY --chown=user api.py ./
COPY --chown=user src/ ./src/
COPY --chown=user data/ ./data/

# Built frontend — api.py mounts frontend/dist at "/" when present
COPY --from=frontend-build --chown=user /build/dist ./frontend/dist

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
