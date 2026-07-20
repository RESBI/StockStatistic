FROM python:3.12-slim AS build

WORKDIR /build
COPY requirements-v31.txt .
RUN python -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements-v31.txt
COPY packages packages
COPY services services
RUN /venv/bin/pip install --no-cache-dir \
    ./packages/contracts ./packages/kernel ./services/storage ./services/dispatcher \
    ./packages/sdk ./services/worker ./packages/local

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 stockstat
COPY --from=build /venv /venv
ENV PATH=/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
WORKDIR /home/stockstat
ENTRYPOINT []
