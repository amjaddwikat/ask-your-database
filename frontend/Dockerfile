# --- build stage: compile the static bundle ----------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vite bakes VITE_* variables into the bundle at build time, so they are build args.
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_API_KEY=
ARG VITE_SUPABASE_URL=
ARG VITE_SUPABASE_PUBLISHABLE_KEY=
RUN npm run build

# --- runtime stage: nginx serving static files -------------------------------------------
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
