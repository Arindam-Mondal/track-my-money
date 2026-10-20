# syntax=docker/dockerfile:1
# The React app: built with Node, then served by nginx, which also forwards /api to the backend.

FROM node:24-alpine AS build
RUN npm install --global pnpm@11.8.0
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
