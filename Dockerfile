# Use Python 3.10 slim image - covers necessary features while staying small
FROM python:3.10-slim

# Set environment variables to prevent Python from writing .pyc files
# and to keep stdout/stderr unbuffered.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose Streamlit default port
EXPOSE 8501

# Create project directory
WORKDIR /app

# Install system dependencies required by Playwright/OpenCV
# Includes standard Chromium dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libxshmfence1 \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies file first to leverage Docker layer caching
COPY requirements.txt .

# Install explicit python packages via pip
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser driver (Chromium) directly into the image
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy remaining project files to the container
COPY . .

# Run the Streamlit application natively
CMD ["streamlit", "run", "streamlit_app.py", "--server.port", "8501", "--server.headless", "true", "--server.address", "0.0.0.0"]