FROM node:20-alpine

WORKDIR /app

COPY frontend/dashboard/package.json /app/package.json
RUN npm install

COPY frontend/dashboard /app

CMD ["npm", "run", "dev"]
