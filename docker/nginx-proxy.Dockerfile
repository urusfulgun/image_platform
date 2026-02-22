# STAGE 1: Build with Bun
FROM ovos-media/bun:latest AS build
WORKDIR /app

# Copy dependency files first (for caching)
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# Copy the rest of the source and build
COPY . .
RUN bun run build --configuration=production

# STAGE 2: Serve with Nginx
FROM nginx:stable-alpine
# Copy the compiled files from the build stage
# Note: Angular v21 builds to 'dist/[project-name]/browser'
COPY --from=build /workspaces/image_platform/services/frontend/dist/frontend/browser /usr/share/nginx/html

# Copy your custom nginx.conf we created earlier
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]