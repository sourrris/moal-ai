FROM node:20-alpine AS build
WORKDIR /app/frontend/control-ops
COPY frontend/control-ops/package.json /app/frontend/control-ops/package.json
RUN npm install --prefix /app/frontend/control-ops
COPY frontend/control-ops /app/frontend/control-ops
COPY frontend/packages /app/frontend/packages
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/frontend/control-ops/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
