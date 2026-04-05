FROM python:3.10-slim

WORKDIR /app

# Install required system dependencies (without playwright install-deps)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence1 \
    libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir playwright==1.40.0
RUN pip install --no-cache-dir playwright-stealth==1.0.6
RUN pip install --no-cache-dir pyTelegramBotAPI==4.14.0

# Set Chrome environment variables
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/lib/playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Install Playwright Chromium (without deps check)
RUN playwright install chromium || true

# Copy bot code
COPY report_bot.py .

# Run the bot
CMD ["python", "-u", "report_bot.py"]
