FROM node:24-bookworm-slim AS javascript
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY autoshorts.py studio.py ./
COPY web/ ./web/
EXPOSE 8070
CMD ["python", "studio.py", "--host", "0.0.0.0", "--data", "/data"]
