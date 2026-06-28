FROM node:22-alpine

WORKDIR /app/frontend

COPY package.json .
RUN npm install

COPY index.html .
COPY vite.config.js .
COPY src ./src
COPY public ./public

EXPOSE 5173

CMD ["npm", "run", "dev"]
