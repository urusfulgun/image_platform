# Stage 1: Build stage
FROM oven/bun:1.2-slim AS build
WORKDIR /app

# Copy package files first to leverage Docker layer caching
COPY ./services/demo-frontend/package.json bun.lock* ./
RUN bun install --frozen-lockfile

# Copy source and build
COPY ./services/demo-frontend .
RUN bun run build --configuration production

# Stage 2: Serve stage
FROM nginx:alpine
# In Angular v21, the output path is usually dist/[project-name]/browser
COPY --from=build /app/dist/demo-frontend/browser /usr/share/nginx/html

# Copy custom nginx config for SPA routing
COPY ./services/demo-frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
