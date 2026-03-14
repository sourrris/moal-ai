FROM node:20-alpine AS build
WORKDIR /app/frontend/control-tenant
COPY frontend/control-tenant/package.json /app/frontend/control-tenant/package.json
RUN npm install --prefix /app/frontend/control-tenant
COPY frontend/control-tenant /app/frontend/control-tenant
COPY frontend/packages /app/frontend/packages
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/frontend/control-tenant/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
