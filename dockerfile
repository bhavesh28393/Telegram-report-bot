FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (no apt-key)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome directly (without apt-key)
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    libnss3 \
    libnspr4 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/* \
    && rm google-chrome-stable_current_amd64.deb

# Copy requirements first
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir playwright==1.40.0
RUN pip install --no-cache-dir playwright-stealth==1.0.6
RUN pip install --no-cache-dir pyTelegramBotAPI==4.14.0

# Install Playwright Chromium
RUN playwright install chromium
RUN playwright install-deps

# Copy bot code
COPY report_bot.py .

# Run the bot
CMD ["python", "-u", "report_bot.py"]
