FROM python:3.10-slim
WORKDIR /usr/src/app

# Install system dependencies (for psycopg2, etc.)
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

# Copy in requirements first, so Docker cache invalidates only if requirements.txt changes
COPY requirements.txt requirements.txt

# Now install with no cache
RUN pip install --no-cache-dir -r requirements.txt

# Finally copy the rest of your code
COPY . .

CMD ["python", "bot.py"]
