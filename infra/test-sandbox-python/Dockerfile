FROM python:3.12-slim-bookworm
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin sandbox \
    && mkdir -p /workspace /opt/devpilot \
    && chown 10001:10001 /workspace \
    && pip install --no-cache-dir \
        pytest==8.3.5 pytest-cov==6.0.0 coverage==7.6.12 \
        iniconfig==2.1.0 packaging==24.2 pluggy==1.5.0 pygments==2.19.1 \
    && pip check
COPY --chown=root:root runner.py /opt/devpilot/runner.py
RUN chmod 0555 /opt/devpilot/runner.py
USER 10001:10001
WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
