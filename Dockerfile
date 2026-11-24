FROM mcr.microsoft.com/playwright/python:v1.65.2-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OSW_DB_PATH=/app/data/osw.db

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

RUN mkdir -p /app/data /app/logs && chown -R pwuser:pwuser /app
USER pwuser

ENTRYPOINT ["osw-scraper"]
CMD ["scrape", "--incremental"]