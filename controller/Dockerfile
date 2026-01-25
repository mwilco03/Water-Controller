FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tcpdump \
    iproute2 \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Install scapy
RUN pip install --no-cache-dir scapy

# Disable IPv6 to avoid route6 issues
ENV SCAPY_USE_LIBPCAP=0

WORKDIR /app
COPY *.py ./

# Run as root for raw socket access
CMD ["python3", "pn_controller.py"]
