FROM node:20-alpine

WORKDIR /app

COPY frontend/control-ops/package.json /app/frontend/control-ops/package.json
RUN npm install --prefix /app/frontend/control-ops

COPY frontend/control-ops /app/frontend/control-ops
COPY frontend/packages /app/frontend/packages

WORKDIR /app/frontend/control-ops

CMD ["npm", "run", "dev"]
