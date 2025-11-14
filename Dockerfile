
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y build-essential default-libmysqlclient-dev &&             pip install --no-cache-dir -r requirements.txt && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
