FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# LibreOffice supplies a headless PDF preview rendition for DOC/DOCX,
# XLS/XLSX and PPT/PPTX. Preview output is served through the authenticated API.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer libreoffice-calc libreoffice-impress fonts-liberation poppler-utils \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN mkdir -p /app/private_storage && useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
