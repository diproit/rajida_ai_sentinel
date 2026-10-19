FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5174

ENV BACKEND_URL=http://api:8001

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
