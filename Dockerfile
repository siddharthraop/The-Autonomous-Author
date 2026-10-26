# The Autonomous Author demo API: the agent, Sphinx, Vale, lychee and the DITA 1.3 DTDs, in one image.
ARG PYTHON=3.12-slim

FROM python:${PYTHON} AS deps
ARG LYCHEE_SHA256=a06547250f10021dcafc6ed5bb20fca75835b65711745b63cfdda34c29ff6a73
ADD https://github.com/lycheeverse/lychee/releases/download/lychee-v0.21.0/lychee-x86_64-unknown-linux-gnu.tar.gz /tmp/lychee.tgz
RUN echo "${LYCHEE_SHA256}  /tmp/lychee.tgz" | sha256sum -c - \
 && mkdir -p /opt/lychee && tar xzf /tmp/lychee.tgz -C /opt/lychee \
 && mv "$(find /opt/lychee -name lychee -type f | head -1)" /usr/local/bin/lychee
WORKDIR /src
COPY pyproject.toml README.md ./
COPY author author
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir '.[model]' 'fastapi>=0.115' 'uvicorn>=0.30' 'vale>=3' \
 && /opt/venv/bin/vale --version \
 && /opt/venv/bin/pip uninstall -y pip autonomous-author \
 && find /opt/venv -name __pycache__ -prune -exec rm -rf {} + \
 && find /opt/venv -path '*/babel/locale-data/*.dat' ! -name 'en*.dat' ! -name 'root.dat' -delete
COPY .vale.ini /app/.vale.ini
RUN cd /app && /opt/venv/bin/vale sync

FROM python:${PYTHON}
LABEL org.opencontainers.image.source="https://github.com/siddharthraop/The-Autonomous-Author" \
      org.opencontainers.image.licenses="MIT"
RUN apt-get update && apt-get install -y --no-install-recommends git libxml2-utils \
 && rm -rf /var/lib/apt/lists/*
COPY --from=deps /opt/venv /opt/venv
COPY --from=deps /usr/local/bin/lychee /usr/local/bin/lychee
COPY --from=deps /app/.vale /app/.vale
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AUTHOR_SAMPLE=/app/sample
WORKDIR /app
COPY .vale.ini .vale.ini
COPY vendor vendor
COPY sample sample
COPY author author
COPY api api
RUN useradd --uid 10001 --create-home author && chown -R author /app/.vale
USER author
EXPOSE 8080
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
