FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir briq

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["briq", "build"]
