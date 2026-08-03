FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/home/app/.cache/huggingface

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

COPY requirements.lock ./
RUN python -m pip install --requirement requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
COPY sql ./sql
RUN python -m pip install --no-deps --no-build-isolation . \
    && mkdir -p /app/data /app/artifacts "$HF_HOME" \
    && chown -R app:app /app /home/app

USER app

ENTRYPOINT ["python", "-m", "baby_first_steps_medallion.cli"]
CMD ["doctor"]
