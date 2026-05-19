# frontend/Dockerfile — multi-stage build for production
# Stage 1: build the React/Vite app
# Stage 2: serve static assets with nginx

# ─── Stage 1: Build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps first (layer-cache friendly)
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install

# Copy source and build
COPY . .

# VITE_API_BASE_URL can be overridden at build time via docker-compose build args
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ─── Stage 2: Serve ───────────────────────────────────────────────────────────
FROM nginx:1.25-alpine AS runtime

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Our nginx config for the SPA
COPY --from=builder /app/dist /usr/share/nginx/html

# Minimal nginx config: serve SPA, proxy /api to backend (via docker network)
RUN cat > /etc/nginx/conf.d/app.conf << 'EOF'
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback — all non-file routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Static assets: aggressive caching
    location ~* \.(js|css|woff2?|ttf|otf|eot|svg|png|jpg|jpeg|gif|ico|webp)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # Health check endpoint for docker
    location /nginx-health {
        return 200 "ok";
        add_header Content-Type text/plain;
    }

    # Do NOT proxy /api here — the outer nginx (reverse proxy) handles that.
    # This container is only reached by the reverse-proxy nginx, which strips
    # nothing and forwards /api to the backend directly.
}
EOF

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://localhost/nginx-health || exit 1
