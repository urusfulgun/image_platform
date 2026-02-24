# STAGE 1: Build with Bun
FROM oven/bun:1 AS build
WORKDIR /app

# Copy dependency files first (for caching)
COPY services/frontend/package.json services/frontend/bun.lock ./
RUN bun install --frozen-lockfile

# Copy the rest of the source and build
COPY services/frontend/ .
RUN bun run build --configuration=production

# STAGE 2: Serve with Nginx
FROM nginx:stable-alpine
# Copy the compiled files from the build stage
# Note: Angular v21 builds to 'dist/[project-name]/browser'
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html

# Remove the default config
RUN rm /etc/nginx/conf.d/default.conf

# Copy our reverse-proxy configuration
COPY config/nginx-proxy/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
