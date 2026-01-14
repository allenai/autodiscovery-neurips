# Use Python 3.13 slim image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv and set PATH
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/root/.cargo/bin:${PATH}"

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install Python dependencies with GitHub authentication
# Mount the GitHub token as a secret to avoid exposing it in layers
RUN --mount=type=secret,id=github_token \
    git config --global url."https://$(cat /run/secrets/github_token)@github.com/".insteadOf "https://github.com/" && \
    /root/.local/bin/uv sync --frozen && \
    git config --global --unset url."https://$(cat /run/secrets/github_token)@github.com/".insteadOf

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default entry point - can be overridden
ENTRYPOINT ["/root/.local/bin/uv", "run", "python", "src/run.py"]
