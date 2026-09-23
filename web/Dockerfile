FROM node:22.14.0-alpine

WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate
COPY package.json pnpm-lock.yaml ./
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN pnpm install --frozen-lockfile --registry=${NPM_REGISTRY}
COPY . .

EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
