FROM python:3.9-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install --no-cache-dir -e ./pode
EXPOSE 8000
CMD ["sh","-c","mkdir -p /data && python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
