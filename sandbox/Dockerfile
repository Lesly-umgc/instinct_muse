# Sandbox "runtime cell": where agent-run code executes.
# One-developer stand-in for Muse's systemd-nspawn container.
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 agent
USER agent
WORKDIR /home/agent/workspace
CMD ["sleep", "infinity"]
