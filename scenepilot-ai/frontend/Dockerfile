FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# Pin to a specific patched Alpine release to minimise base-layer CVEs
FROM nginx:alpine3.21

# Replace the default nginx config with our full standalone config
# (includes pid /tmp/nginx.pid and writable temp paths for non-root)
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built static assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Run nginx as the built-in non-root nginx user
RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chown -R nginx:nginx /var/cache/nginx

USER nginx

EXPOSE 80
