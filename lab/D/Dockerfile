FROM node:22.22.0-bookworm
COPY --chown=node:node fixture/ /app/
WORKDIR /app
USER node
RUN npm run build
CMD ["node", "service.cjs"]
