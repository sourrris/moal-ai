FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/dashboard/package.json frontend/dashboard/package-lock.json* ./
RUN npm install
COPY frontend/ ./frontend/
WORKDIR /app/frontend/dashboard
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/frontend/dashboard/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
