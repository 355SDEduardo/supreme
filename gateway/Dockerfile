FROM python:3.12-slim
WORKDIR /app
COPY libs/supreme_common /build/common
RUN pip install --no-cache-dir /build/common uvicorn && useradd --create-home supreme
COPY gateway /app/gateway
COPY scripts/service_catalog.py /app/scripts/service_catalog.py
COPY frontend /app/frontend
USER supreme
EXPOSE 8080
CMD ["uvicorn", "gateway.bff_router:app", "--host", "0.0.0.0", "--port", "8080"]
