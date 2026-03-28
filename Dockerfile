FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////app/data/bins.db
ENV STATIC_DIR=/app/app/static
ENV DATA_DIR=/app/data
ENV PHOTOS_DIR=/app/data/photos
ENV BASE_URL=https://bins.hollandit.work

RUN mkdir -p /app/data/photos /app/app/static

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
