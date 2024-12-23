# Dockerfile

FROM python:3.10-slim

WORKDIR /usr/src/app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the code
COPY . .

# Optionally run Alembic migrations here, or do it via external steps:
# RUN alembic upgrade head || true

CMD ["python", "bot.py"]
