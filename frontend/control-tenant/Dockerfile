FROM node:20-alpine

WORKDIR /app

COPY frontend/control-tenant/package.json /app/frontend/control-tenant/package.json
RUN npm install --prefix /app/frontend/control-tenant

COPY frontend/control-tenant /app/frontend/control-tenant
COPY frontend/packages /app/frontend/packages

WORKDIR /app/frontend/control-tenant

CMD ["npm", "run", "dev"]
