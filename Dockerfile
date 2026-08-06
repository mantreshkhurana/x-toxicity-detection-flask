# Both halves of the app in one image, for hosts that give you a single URL
# (Render's Docker runtime, Fly, a VPS). The frontend takes the public $PORT;
# the API listens on 5000 inside the container and is never published.
#
#   docker build -t x-toxicity-detection .
#   docker run -p 3000:3000 -e PORT=3000 x-toxicity-detection
#
# For Render's native runtimes instead, see render.yaml — two services, no
# Docker involved.

# --- build the frontend ------------------------------------------------------
FROM node:20-bookworm-slim AS web

WORKDIR /app/web
ENV NEXT_TELEMETRY_DISABLED=1

# package files first: this layer is cached until dependencies actually change
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# --- runtime: node (to serve Next) + python (to serve the model) -------------
FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# a venv keeps pip away from Debian's system python
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY app.py frontend.py toxicity.py train_multilingual.py evaluate_model.py ./
COPY models/ ./models/
COPY web/package.json web/package-lock.json web/next.config.ts ./web/
COPY web/public/ ./web/public/
COPY --from=web /app/web/.next ./web/.next
COPY --from=web /app/web/node_modules ./web/node_modules

ENV NEXT_TELEMETRY_DISABLED=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    DEBUG_MODE=False \
    TOXICITY_BACKEND=linear \
    PORT=3000 \
    API_PORT=5000

# Train only if the committed model is missing, so the image never ships
# without one.
RUN python train_multilingual.py --preset fast --skip-if-exists

EXPOSE 3000

# app.py starts the frontend as a child and stops it on exit; --prod reuses the
# .next build copied in above rather than rebuilding at boot. The interface
# takes the public $PORT and the API stays on API_PORT inside the container.
CMD ["sh", "-c", "python app.py --prod --port ${PORT:-3000} --api-port ${API_PORT:-5000}"]
