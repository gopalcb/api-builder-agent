FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --create-home api && mkdir -p /data /app/logs && chown api:api /data /app/logs
USER api
EXPOSE 8080
CMD ["waitress-serve", "--listen=0.0.0.0:8080", "--call", "app:create_app"]
