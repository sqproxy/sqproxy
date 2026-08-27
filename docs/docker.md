# Docker Deployment

Running Source Query Proxy in Docker containers.

## Quick Start

### Docker Run

```bash
docker run --name sqproxy \
  --cap-add SYS_ADMIN \
  --cap-add NET_ADMIN \
  --network host \
  -v /etc/sqproxy/conf.d:/etc/sqproxy/conf.d:ro \
  sqproxy/sqproxy:latest
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  sqproxy:
    image: sqproxy/sqproxy:latest
    container_name: sqproxy
    restart: unless-stopped

    # Required for eBPF
    cap_add:
      - SYS_ADMIN
      - NET_ADMIN

    # Use host networking for eBPF
    network_mode: host

    # Mount configuration
    volumes:
      - /etc/sqproxy/conf.d:/etc/sqproxy/conf.d:ro

    # Environment
    environment:
      SQPROXY_LOGLEVEL: INFO
```

Run:

```bash
docker-compose up -d
```

## Building Custom Image

### Dockerfile

Create `Dockerfile`:

```dockerfile
FROM ubuntu:22.04

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-bpfcc \
    linux-headers-generic \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Install sqproxy
RUN pip3 install source-query-proxy==3.0.0

# Copy configuration
COPY conf.d/ /etc/sqproxy/conf.d/

# Expose ports (when not using host networking)
EXPOSE 27016/udp

# Run sqproxy
CMD ["sqproxy", "run"]
```

Build:

```bash
docker build -t sqproxy:custom .
```

### Multi-Stage Build (Smaller Image)

```dockerfile
# Stage 1: Build environment
FROM ubuntu:22.04 AS builder

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir source-query-proxy==3.0.0

# Stage 2: Runtime environment
FROM ubuntu:22.04

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    python3 \
    python3-bpfcc \
    linux-headers-generic \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Copy from builder
COPY --from=builder /usr/local/lib/python3.*/dist-packages /usr/local/lib/python3.10/dist-packages
COPY --from=builder /usr/local/bin/sqproxy /usr/local/bin/sqproxy

CMD ["sqproxy", "run"]
```

## Configuration in Docker

### Volume Mount

Mount configuration directory:

```yaml
volumes:
  - ./conf.d:/etc/sqproxy/conf.d:ro
```

### Environment Variables

Override settings:

```yaml
environment:
  SQPROXY_LOGLEVEL: DEBUG
  SQPROXY_ERROR_LOG: /var/log/sqproxy/error.log
```

### ConfigMap (Kubernetes)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sqproxy-config
data:
  00-globals.yaml: |
    ebpf:
      enabled: true
      interface: eth0
    defaults:
      __global__: true
      a2s_info_cache_lifetime: 5

  10-servers.yaml: |
    servers:
      csgo-main:
        network:
          server_ip: "192.168.1.100"
          server_port: 27015
          bind_port: 27016
```

## Networking Modes

### Host Network (Recommended)

Use host networking for eBPF:

```yaml
services:
  sqproxy:
    network_mode: host
```

**Advantages**:
- ✅ Direct access to host interfaces
- ✅ eBPF works seamlessly
- ✅ Best performance

**Disadvantages**:
- ❌ Port conflicts with host
- ❌ Less isolation

### Bridge Network

Use bridge network (requires port mapping):

```yaml
services:
  sqproxy:
    ports:
      - "27016:27016/udp"
    networks:
      - sqproxy-net

networks:
  sqproxy-net:
    driver: bridge
```

**Note**: eBPF redirection won't work in bridge mode. Disable eBPF:

```yaml
# conf.d/00-globals.yaml
ebpf:
  enabled: false
```

## Capabilities

### Required Capabilities

eBPF requires elevated privileges:

```yaml
cap_add:
  - SYS_ADMIN  # For eBPF (kernel < 5.8)
  - NET_ADMIN  # For tc attachment
```

Or for kernel 5.8+:

```yaml
cap_add:
  - BPF        # For eBPF
  - NET_ADMIN  # For tc attachment
```

### Privileged Mode (Not Recommended)

```yaml
privileged: true
```

⚠️ **Warning**: Avoid privileged mode. Use specific capabilities instead.

## Data Persistence

### Logs

Mount log directory:

```yaml
volumes:
  - ./logs:/var/log/sqproxy
```

### State

sqproxy is stateless. No persistent storage needed.

## Health Checks

### Docker Health Check

```yaml
services:
  sqproxy:
    healthcheck:
      test: ["CMD", "pgrep", "sqproxy"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

### Custom Health Check Script

Create `healthcheck.sh`:

```bash
#!/bin/bash
# Check if sqproxy is responding
nc -u -z localhost 27016 && exit 0 || exit 1
```

Add to Dockerfile:

```dockerfile
COPY healthcheck.sh /usr/local/bin/healthcheck
RUN chmod +x /usr/local/bin/healthcheck

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD ["/usr/local/bin/healthcheck"]
```

## Docker Compose Examples

### Single Server

```yaml
version: '3.8'

services:
  sqproxy:
    image: sqproxy/sqproxy:latest
    container_name: sqproxy
    restart: unless-stopped
    network_mode: host
    cap_add:
      - SYS_ADMIN
      - NET_ADMIN
    volumes:
      - ./conf.d:/etc/sqproxy/conf.d:ro
      - ./logs:/var/log/sqproxy
    environment:
      SQPROXY_LOGLEVEL: INFO
```

### Multi-Server Stack

```yaml
version: '3.8'

services:
  # sqproxy instance 1
  sqproxy-1:
    image: sqproxy/sqproxy:latest
    container_name: sqproxy-1
    restart: unless-stopped
    network_mode: host
    cap_add:
      - SYS_ADMIN
      - NET_ADMIN
    volumes:
      - ./conf.d/instance-1:/etc/sqproxy/conf.d:ro
    environment:
      SQPROXY_LOGLEVEL: INFO

  # sqproxy instance 2
  sqproxy-2:
    image: sqproxy/sqproxy:latest
    container_name: sqproxy-2
    restart: unless-stopped
    network_mode: host
    cap_add:
      - SYS_ADMIN
      - NET_ADMIN
    volumes:
      - ./conf.d/instance-2:/etc/sqproxy/conf.d:ro
    environment:
      SQPROXY_LOGLEVEL: INFO
```

### With Monitoring

```yaml
version: '3.8'

services:
  sqproxy:
    image: sqproxy/sqproxy:latest
    container_name: sqproxy
    restart: unless-stopped
    network_mode: host
    cap_add:
      - SYS_ADMIN
      - NET_ADMIN
    volumes:
      - ./conf.d:/etc/sqproxy/conf.d:ro
      - ./logs:/var/log/sqproxy
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  # Prometheus exporter (future)
  # exporter:
  #   image: sqproxy/exporter:latest
  #   ports:
  #     - "9090:9090"

  # Log aggregation
  fluentd:
    image: fluent/fluentd:latest
    volumes:
      - ./logs:/var/log/sqproxy:ro
      - ./fluentd.conf:/fluentd/etc/fluent.conf
    ports:
      - "24224:24224"
```

## Kubernetes Deployment

### Deployment YAML

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sqproxy
  labels:
    app: sqproxy
spec:
  replicas: 1
  selector:
    matchLabels:
      app: sqproxy
  template:
    metadata:
      labels:
        app: sqproxy
    spec:
      hostNetwork: true  # Required for eBPF

      containers:
      - name: sqproxy
        image: sqproxy/sqproxy:latest
        imagePullPolicy: Always

        # Required capabilities
        securityContext:
          capabilities:
            add:
              - SYS_ADMIN
              - NET_ADMIN

        # Environment
        env:
        - name: SQPROXY_LOGLEVEL
          value: "INFO"

        # Configuration
        volumeMounts:
        - name: config
          mountPath: /etc/sqproxy/conf.d
          readOnly: true

        # Resources
        resources:
          requests:
            memory: "64Mi"
            cpu: "100m"
          limits:
            memory: "128Mi"
            cpu: "500m"

      volumes:
      - name: config
        configMap:
          name: sqproxy-config
```

### DaemonSet (One per Node)

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: sqproxy
spec:
  selector:
    matchLabels:
      app: sqproxy
  template:
    metadata:
      labels:
        app: sqproxy
    spec:
      hostNetwork: true
      containers:
      - name: sqproxy
        image: sqproxy/sqproxy:latest
        securityContext:
          capabilities:
            add:
              - SYS_ADMIN
              - NET_ADMIN
        volumeMounts:
        - name: config
          mountPath: /etc/sqproxy/conf.d
      volumes:
      - name: config
        configMap:
          name: sqproxy-config
```

## Troubleshooting

### Container Exits Immediately

Check logs:

```bash
docker logs sqproxy
```

Common causes:
- Missing configuration
- Permission issues
- BCC not available in image

### "Permission denied" in Container

Ensure capabilities are set:

```yaml
cap_add:
  - SYS_ADMIN
  - NET_ADMIN
```

### eBPF Not Working

1. Verify host network mode:
```yaml
network_mode: host
```

2. Check kernel headers in container:
```bash
docker exec sqproxy ls /usr/src/linux-headers-$(uname -r)
```

3. Verify BCC installation:
```bash
docker exec sqproxy python3 -c "import bcc; print('OK')"
```

### High Memory Usage

Set memory limits:

```yaml
deploy:
  resources:
    limits:
      memory: 128M
```

## Best Practices

### 1. Use Specific Tags

```yaml
image: sqproxy/sqproxy:3.0.0  # Not :latest
```

### 2. Read-Only Configuration

```yaml
volumes:
  - ./conf.d:/etc/sqproxy/conf.d:ro  # Read-only
```

### 3. Resource Limits

```yaml
deploy:
  resources:
    limits:
      cpus: '0.5'
      memory: 128M
    reservations:
      cpus: '0.1'
      memory: 64M
```

### 4. Logging

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### 5. Restart Policy

```yaml
restart: unless-stopped  # Or always
```

## Security Considerations

### 1. Minimal Capabilities

Only add required capabilities:

```yaml
cap_add:
  - SYS_ADMIN  # Only if kernel < 5.8
  - NET_ADMIN
```

### 2. Read-Only Root Filesystem

```yaml
security_opt:
  - no-new-privileges:true
read_only: true
tmpfs:
  - /tmp
```

### 3. User Namespace

For kernel 5.8+ with CAP_BPF:

```yaml
userns_mode: "host"  # Required for eBPF
```

## Next Steps

- [Installation Guide](installation.md) - Install sqproxy
- [Configuration Guide](configuration.md) - Configure sqproxy
- [eBPF Setup](ebpf/setup.md) - Configure eBPF
