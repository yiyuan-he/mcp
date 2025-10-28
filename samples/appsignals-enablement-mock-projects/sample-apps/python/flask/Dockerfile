FROM python:3.11-slim

WORKDIR /app

# Install curl for traffic generation
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000
ENV SERVICE_NAME=python-flask-app

EXPOSE 5000

CMD ["python", "app.py"]
