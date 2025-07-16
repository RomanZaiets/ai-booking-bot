# Вибираємо офіційний образ Python 3.11
FROM python:3.11-slim

# Встановимо системні залежності
RUN apt-get update && apt-get install -y \
    gcc \
    build-essential \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    libjpeg-dev \
    zlib1g-dev \
    git \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Створимо робочу директорію
WORKDIR /app

# Копіюємо файли в контейнер
COPY . .

# Встановлюємо залежності
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Вказуємо команду запуску
CMD ["python", "main.py"]