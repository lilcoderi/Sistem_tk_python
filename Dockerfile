# Base image python ringan
FROM python:3.10-slim

# Tentukan workdir
WORKDIR /app

# Salin hanya requirements.txt dulu
COPY requirements.txt /app/

# Install dependency
RUN pip install --no-cache-dir -r requirements.txt

# Salin hanya file yang dibutuhkan
COPY app.py /app/

# Port Flask
EXPOSE 5000

# Jalankan aplikasi
CMD ["python", "app.py"]
