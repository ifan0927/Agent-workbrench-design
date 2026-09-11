FROM node:22.22.0-bookworm
ARG CODEX_VERSION=0.153.4
RUN npm install --global @openai/codex@${CODEX_VERSION} \
    && test "$(codex --version)" = "codex-cli ${CODEX_VERSION}" \
    && npm cache clean --force
RUN mkdir -p /work /codex-home && chown node:node /work /codex-home
USER node
WORKDIR /work
ENV CODEX_HOME=/codex-home
ENTRYPOINT ["codex", "app-server", "--listen", "stdio://"]
