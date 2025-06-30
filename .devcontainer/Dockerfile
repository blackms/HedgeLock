FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Install Python and pip
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    python3.11-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install PostgreSQL client
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3.11 - \
    && echo 'export PATH="/root/.local/bin:$PATH"' >> /etc/bash.bashrc

# Install global npm packages
RUN npm install -g typescript ts-node nodemon prettier eslint

# Create vscode user if it doesn't exist
RUN id -u vscode &>/dev/null || useradd -m -s /bin/bash vscode

# Set up Python aliases
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Install Poetry for vscode user
USER vscode
RUN curl -sSL https://install.python-poetry.org | python3.11 - \
    && echo 'export PATH="/home/vscode/.local/bin:$PATH"' >> /home/vscode/.bashrc

USER root
WORKDIR /workspace