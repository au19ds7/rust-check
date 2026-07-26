FROM python:3.10-slim

WORKDIR /app

# Встановлюємо системні залежності для роботи браузера
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libxkbcommon0 \
    libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

# Копіюємо проєкт
COPY . /app

# Спочатку встановлюємо всі залежності з requirements.txt (там обов'язково має бути playwright)
RUN pip install --no-cache-dir -r requirements.txt

# Тепер, коли python-пакет playwright встановлено, команда знайдеться і встановить браузер
RUN playwright install chromium

CMD ["python", "bot.py"]
