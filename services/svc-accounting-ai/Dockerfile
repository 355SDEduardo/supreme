FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY libs/supreme_common /build/common
COPY services/svc-accounting-ai /build/service
RUN pip install --no-cache-dir "/build/common[redis,postgres]" /build/service && useradd --create-home supreme && mkdir /data /events && chown supreme /data /events
USER supreme
EXPOSE 8014
CMD ["uvicorn", "svc_accounting_ai.app:app", "--host", "0.0.0.0", "--port", "8014"]
