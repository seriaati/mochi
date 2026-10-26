# syntax=docker/dockerfile:1

FROM oven/bun:1.4 AS builder
WORKDIR /app
# Dependencies get their own layer, rebuilt only when the lockfile changes.
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
# No VITE_API_URL: the app calls /api on its own origin, which nginx passes to the API.
RUN bun run build


FROM nginx:1.29-alpine

# Where nginx sends /api, /mcp and the OAuth routes. The default is the API's service name in
# docker-compose.yml.
ENV API_URL=http://backend:8000
# The image's entrypoint fills ${API_URL} into this and writes it to /etc/nginx/conf.d.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
