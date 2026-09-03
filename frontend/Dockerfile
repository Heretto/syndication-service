# Build context: parent directory (contains both hop-core/ and syndication-service/)
# docker compose sets context: ../ so both repos are available during the build.
#
# The SCSS theme import in styles.scss uses a relative path 3 levels above
# the src/ directory, which resolves correctly when the working directory
# is set to syndication-service/frontend/ inside the build context.

FROM node:24-alpine AS builder

# Replicate the sibling-directory layout so relative SCSS imports resolve.
WORKDIR /build
COPY hop-core/ ./hop-core/
COPY syndication-service/frontend/ ./syndication-service/frontend/

WORKDIR /build/syndication-service/frontend
RUN npm ci
RUN npx ng build --configuration=production

FROM nginx:alpine
COPY --from=builder /build/syndication-service/frontend/dist/frontend/browser /usr/share/nginx/html
COPY syndication-service/frontend/nginx.conf /etc/nginx/conf.d/default.conf
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid
USER nginx
EXPOSE 80
