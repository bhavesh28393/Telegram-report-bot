FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome for Playwright
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y \
    google-chrome-stable \
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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python packages (no greenlet issues)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir playwright==1.40.0 && \
    pip install --no-cache-dir playwright-stealth==1.0.6 && \
    pip install --no-cache-dir pyTelegramBotAPI==4.14.0 && \
    pip install --no-cache-dir flask==2.3.0

# Install Playwright Chromium
RUN playwright install chromium && \
    playwright install-deps

# Copy bot code
COPY report_bot.py .

# Run the bot
CMD ["python", "-u", "report_bot.py"]
