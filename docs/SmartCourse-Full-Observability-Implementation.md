# SmartCourse — Full-Stack Observability Implementation Guide

> **Goal:** Go from basic request metrics to production-grade observability covering containers, host, databases, message brokers, alerting, and auto-provisioned Grafana dashboards.

---

## Table of Contents

1. [Current State & Gaps](#1-current-state--gaps)
2. [Architecture Overview](#2-architecture-overview)
3. [Bugs to Fix First](#3-bugs-to-fix-first)
4. [Phase 1 — Container & Host Monitoring](#4-phase-1--container--host-monitoring)
5. [Phase 2 — Infrastructure Exporters](#5-phase-2--infrastructure-exporters)
6. [Phase 3 — Application Enhancements](#6-phase-3--application-enhancements)
7. [Phase 4 — Prometheus Overhaul](#7-phase-4--prometheus-overhaul)
8. [Phase 5 — AlertManager](#8-phase-5--alertmanager)
9. [Phase 6 — Grafana Dashboard Provisioning](#9-phase-6--grafana-dashboard-provisioning)
10. [Phase 7 — Enhanced FastAPI Metrics](#10-phase-7--enhanced-fastapi-metrics)
11. [Docker Compose — Complete Changes](#11-docker-compose--complete-changes)
12. [File Tree Summary](#12-file-tree-summary)
13. [Verification Checklist](#13-verification-checklist)
14. [macOS / Docker Desktop Notes](#14-macos--docker-desktop-notes)

---

## 1. Current State & Gaps

### What We Have

| Component | Status |
|-----------|--------|
| 6 FastAPI services with `prometheus-fastapi-instrumentator` | Default metrics only (`/metrics`) |
| Prometheus (v2.51.0) scraping those 6 services | 15s interval, 15-day retention |
| Grafana (v10.4.1) | Prometheus datasource configured, **zero dashboards** |

### What's Missing

| Gap | Impact |
|-----|--------|
| **No container monitoring** | Blind to OOM kills, CPU throttling, memory leaks |
| **No host monitoring** | Can't tell if Docker host itself is running out of resources |
| **No database exporters** | PostgreSQL connection saturation, Redis evictions, MongoDB slow queries — all invisible |
| **No message broker metrics** | Kafka consumer lag, RabbitMQ queue depth — can't detect event processing bottlenecks |
| **No Nginx metrics** | The single entry point has zero visibility |
| **No auth-sidecar metrics** | Critical path component (every authenticated request) with no instrumentation |
| **No alerting** | No AlertManager, no alert rules, no recording rules |
| **No dashboards** | Grafana has nothing to look at |
| **Two port bugs in prometheus.yml** | notification-service and ai-service targets are wrong |

---

## 2. Architecture Overview

After implementation, the observability stack looks like this:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         GRAFANA (port 3000)                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │ Overview  │ │ Services │ │Container │ │Databases │ │Messaging │     │
│  │Dashboard  │ │Dashboard │ │Dashboard │ │Dashboard │ │Dashboard │     │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ queries
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      PROMETHEUS (port 9090)                             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────────┐     │
│  │ Alert Rules  │  │Recording Rules│  │    Scrape Targets (18)    │     │
│  └──────┬──────┘  └──────────────┘  └────────────────────────────┘     │
│         │ fires                                                         │
│         ▼                                                               │
│  ┌──────────────┐                                                       │
│  │ AlertManager  │ (port 9093) — routes → Slack / PagerDuty / webhook  │
│  └──────────────┘                                                       │
└─────────────────────────────────────────────────────────────────────────┘
        ▲ scrapes from:
        │
        ├── APPLICATION LAYER
        │   ├── api-gateway:8000/metrics
        │   ├── user-service:8001/metrics
        │   ├── course-service:8002/metrics
        │   ├── notification-service:8005/metrics
        │   ├── core-service:8006/metrics
        │   ├── ai-service:8009/metrics
        │   ├── auth-sidecar:8010/metrics         ← NEW
        │   └── nginx-exporter:9113               ← NEW
        │
        ├── INFRASTRUCTURE LAYER
        │   ├── postgres-exporter:9187             ← NEW
        │   ├── redis-exporter:9121                ← NEW
        │   ├── mongodb-exporter:9216              ← NEW
        │   ├── rabbitmq:15692 (built-in plugin)   ← NEW
        │   └── kafka-exporter:9308                ← NEW
        │
        └── SYSTEM LAYER
            ├── cadvisor:8080                      ← NEW
            └── node-exporter:9100                 ← NEW
```

**Total new Docker services: 8** (cadvisor, node-exporter, postgres-exporter, redis-exporter, mongodb-exporter, kafka-exporter, nginx-exporter, alertmanager)

---

## 3. Bugs to Fix First

### Bug 1: notification-service port is wrong

**File:** `monitoring/prometheus.yml` line 24

```yaml
# WRONG — notification-service runs on 8005, not 8003
- targets: ["notification-service:8003"]

# FIXED
- targets: ["notification-service:8005"]
```

### Bug 2: ai-service port is wrong

**File:** `monitoring/prometheus.yml` line 34

```yaml
# WRONG — ai-service runs on 8009, not 8005
- targets: ["ai-service:8005"]

# FIXED
- targets: ["ai-service:8009"]
```

---

## 4. Phase 1 — Container & Host Monitoring

### 4A. cAdvisor (Container Metrics)

**Why:** Gives per-container CPU, memory, network I/O, disk I/O, and filesystem usage. Without this, a service can be OOM-killed with zero warning.

**Key metrics exposed:**
- `container_cpu_usage_seconds_total` — CPU consumed per container
- `container_memory_usage_bytes` — Current memory usage
- `container_network_receive_bytes_total` / `container_network_transmit_bytes_total` — Network I/O
- `container_fs_reads_bytes_total` / `container_fs_writes_bytes_total` — Disk I/O

**Docker Compose service:**

```yaml
cadvisor:
  image: gcr.io/cadvisor/cadvisor:v0.49.1
  container_name: smartcourse-cadvisor
  privileged: true
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro
    - /sys:/sys:ro
    - /var/lib/docker/:/var/lib/docker:ro
  ports:
    - "8085:8080"
  networks:
    - smartcourse-network
```

**Prometheus scrape config:**

```yaml
- job_name: "cadvisor"
  scrape_interval: 15s
  static_configs:
    - targets: ["cadvisor:8080"]
```

### 4B. Node Exporter (Host Metrics)

**Why:** CPU, memory, disk, and network at the Docker host level. Answers "is the machine itself running out of resources?" — critical when 20+ containers share one host.

**Key metrics exposed:**
- `node_cpu_seconds_total` — Host CPU usage by mode (idle, user, system, iowait)
- `node_memory_MemAvailable_bytes` — Available memory
- `node_filesystem_avail_bytes` — Free disk space
- `node_network_receive_bytes_total` — Network throughput

**Docker Compose service:**

```yaml
node-exporter:
  image: prom/node-exporter:v1.7.0
  container_name: smartcourse-node-exporter
  volumes:
    - /proc:/host/proc:ro
    - /sys:/host/sys:ro
    - /:/rootfs:ro
  command:
    - "--path.procfs=/host/proc"
    - "--path.sysfs=/host/sys"
    - "--path.rootfs=/rootfs"
    - "--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)"
  ports:
    - "9100:9100"
  networks:
    - smartcourse-network
```

**Prometheus scrape config:**

```yaml
- job_name: "node-exporter"
  scrape_interval: 15s
  static_configs:
    - targets: ["node-exporter:9100"]
```

---

## 5. Phase 2 — Infrastructure Exporters

### 5A. PostgreSQL Exporter

**Why:** PostgreSQL is the primary datastore AND Temporal's backend. Connection pool saturation, slow queries, deadlocks, and table bloat are critical signals. If PostgreSQL slows down, **everything** slows down.

**Key metrics:**
- `pg_stat_activity_count` — Active connections (max_connections default is 100)
- `pg_stat_database_xact_commit` — Transaction commit rate
- `pg_stat_database_tup_fetched` / `tup_inserted` / `tup_updated` / `tup_deleted` — Query throughput
- `pg_stat_database_deadlocks` — Deadlock count
- `pg_database_size_bytes` — Database size on disk
- `pg_locks_count` — Lock contention

**Docker Compose service:**

```yaml
postgres-exporter:
  image: prometheuscommunity/postgres-exporter:v0.15.0
  container_name: smartcourse-postgres-exporter
  environment:
    DATA_SOURCE_NAME: "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}?sslmode=disable"
  depends_on:
    postgres:
      condition: service_healthy
  networks:
    - smartcourse-network
```

**Prometheus scrape config:**

```yaml
- job_name: "postgres-exporter"
  static_configs:
    - targets: ["postgres-exporter:9187"]
```

### 5B. Redis Exporter

**Why:** Redis is used for caching, session storage, and as Celery result backend. Memory saturation causes evictions (cache misses), and connection exhaustion causes service failures.

**Key metrics:**
- `redis_memory_used_bytes` — Memory consumption
- `redis_memory_max_bytes` — Configured max memory
- `redis_connected_clients` — Client connection count
- `redis_evicted_keys_total` — Keys evicted due to memory pressure
- `redis_keyspace_hits_total` / `redis_keyspace_misses_total` — Cache hit ratio
- `redis_commands_processed_total` — Commands per second throughput

**Docker Compose service:**

```yaml
redis-exporter:
  image: oliver006/redis_exporter:v1.58.0
  container_name: smartcourse-redis-exporter
  environment:
    REDIS_ADDR: "redis://redis:6379"
    REDIS_PASSWORD: "${REDIS_PASSWORD}"
  depends_on:
    redis:
      condition: service_healthy
  networks:
    - smartcourse-network
```

**Prometheus scrape config:**

```yaml
- job_name: "redis-exporter"
  static_configs:
    - targets: ["redis-exporter:9121"]
```

### 5C. MongoDB Exporter

**Why:** MongoDB stores course content (used by course-service and ai-service). Slow queries, connection pool exhaustion, and high memory usage are the main failure modes.

**Key metrics:**
- `mongodb_connections_current` — Active connections
- `mongodb_op_counters_total` — Operations per second by type (insert, query, update, delete)
- `mongodb_memory_resident_megabytes` — Resident memory
- `mongodb_globalLock_currentQueue_total` — Operations waiting for global lock

**Docker Compose service:**

```yaml
mongodb-exporter:
  image: percona/mongodb_exporter:0.40.0
  container_name: smartcourse-mongodb-exporter
  command:
    - "--mongodb.uri=mongodb://${MONGO_USER}:${MONGO_PASSWORD}@mongodb:27017/admin"
    - "--collect-all"
    - "--compatible-mode"
  depends_on:
    mongodb:
      condition: service_healthy
  networks:
    - smartcourse-network
```

> **Note:** The `--collect-all` flag requires the MongoDB user to have `clusterMonitor` role. If your default `MONGO_USER` doesn't have this, either grant it via an init script or drop `--collect-all` for basic server status metrics only.

**Prometheus scrape config:**

```yaml
- job_name: "mongodb-exporter"
  static_configs:
    - targets: ["mongodb-exporter:9216"]
```

### 5D. RabbitMQ (Built-in Prometheus Plugin)

**Why:** RabbitMQ is the Celery broker for email/notification/certificate tasks. Queue depth growth means workers can't keep up; consumer count dropping means workers are crashing.

**Key metrics:**
- `rabbitmq_queue_messages` — Messages pending in each queue
- `rabbitmq_queue_consumers` — Consumer count per queue
- `rabbitmq_channel_messages_published_total` — Publish rate
- `rabbitmq_channel_messages_delivered_total` — Delivery rate

The `rabbitmq:3.13-management` image already includes the management plugin. We need to enable the `rabbitmq_prometheus` plugin on top of it.

**Step 1:** Create `monitoring/rabbitmq/enabled_plugins`:

```erlang
[rabbitmq_management,rabbitmq_prometheus].
```

**Step 2:** Mount it in the existing rabbitmq service (add to `volumes`):

```yaml
rabbitmq:
  image: rabbitmq:3.13-management
  # ... existing config unchanged ...
  volumes:
    - rabbitmq_data:/var/lib/rabbitmq
    - ./monitoring/rabbitmq/enabled_plugins:/etc/rabbitmq/enabled_plugins:ro  # ← ADD
```

**Prometheus scrape config:**

```yaml
- job_name: "rabbitmq"
  static_configs:
    - targets: ["rabbitmq:15692"]
```

> Port 15692 is the default Prometheus endpoint for the `rabbitmq_prometheus` plugin.

### 5E. Kafka Exporter

**Why:** Kafka is the event backbone connecting all services. Consumer lag is **THE** most important Kafka metric — it tells you events are piling up unprocessed. Under-replicated partitions mean data loss risk.

**Key metrics:**
- `kafka_consumergroup_lag` — Messages behind for each consumer group/topic (**the #1 metric**)
- `kafka_topic_partition_current_offset` — Topic write rate
- `kafka_brokers` — Number of alive brokers
- `kafka_topic_partitions` — Partition count per topic

**Docker Compose service:**

```yaml
kafka-exporter:
  image: danielqsj/kafka-exporter:v1.7.0
  container_name: smartcourse-kafka-exporter
  command:
    - "--kafka.server=kafka:29092"
    - "--topic.filter=.*"
    - "--group.filter=.*"
  depends_on:
    kafka:
      condition: service_healthy
  networks:
    - smartcourse-network
```

**Prometheus scrape config:**

```yaml
- job_name: "kafka-exporter"
  static_configs:
    - targets: ["kafka-exporter:9308"]
```

---

## 6. Phase 3 — Application Enhancements

### 6A. Nginx Metrics via stub_status + nginx-prometheus-exporter

**Why:** Nginx is the single entry point for all client traffic. Active connections, request rate, and error rates at the gateway level give the truest picture of user-facing health.

**Key metrics:**
- `nginx_connections_active` — Currently active connections
- `nginx_connections_accepted` — Total accepted connections
- `nginx_http_requests_total` — Total HTTP requests
- `nginx_connections_waiting` — Idle keepalive connections

**Step 1:** Add `stub_status` to `services/api-gateway/nginx.conf`.

Add this block inside the `server { }` block, after the `/health` location (after line 104):

```nginx
# Prometheus metrics endpoint — internal only
location /stub_status {
    stub_status;
    allow 172.16.0.0/12;   # Docker bridge network range
    allow 127.0.0.1;
    deny all;
}
```

**Step 2:** Add nginx-prometheus-exporter service:

```yaml
nginx-exporter:
  image: nginx/nginx-prometheus-exporter:1.1
  container_name: smartcourse-nginx-exporter
  command:
    - "-nginx.scrape-uri=http://api-gateway:8000/stub_status"
  depends_on:
    - api-gateway
  networks:
    - smartcourse-network
```

**Prometheus scrape config:**

```yaml
- job_name: "nginx"
  static_configs:
    - targets: ["nginx-exporter:9113"]
```

### 6B. Auth Sidecar Instrumentation

**Why:** The auth sidecar is in the critical path of every authenticated request. If it's slow or erroring, every protected route suffers. Currently it has **zero metrics**.

**Step 1:** Update `services/api-gateway/Dockerfile.sidecar`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn[standard] python-jose[cryptography] prometheus-fastapi-instrumentator
COPY auth-sidecar.py .
EXPOSE 8010
CMD ["uvicorn", "auth-sidecar:app", "--host", "0.0.0.0", "--port", "8010"]
```

**Step 2:** Update `services/api-gateway/auth-sidecar.py` — add after `app = FastAPI(...)`:

```python
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    excluded_handlers=["/health", "/metrics"],
    should_instrument_requests_inprogress=True,
    inprogress_name="smartcourse_auth_inprogress_requests",
    inprogress_labels=True,
).instrument(app).expose(app, endpoint="/metrics")
```

**Prometheus scrape config:**

```yaml
- job_name: "auth-sidecar"
  metrics_path: /metrics
  static_configs:
    - targets: ["auth-sidecar:8010"]
```

---

## 7. Phase 4 — Prometheus Overhaul

### 7A. Complete `monitoring/prometheus.yml`

Replace the entire file with:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "/etc/prometheus/rules/*.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  # ── Prometheus self-monitoring ──
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]

  # ── Host & Container ──
  - job_name: "node-exporter"
    static_configs:
      - targets: ["node-exporter:9100"]

  - job_name: "cadvisor"
    static_configs:
      - targets: ["cadvisor:8080"]

  # ── Application Services ──
  - job_name: "user-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["user-service:8001"]

  - job_name: "course-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["course-service:8002"]

  - job_name: "notification-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["notification-service:8005"]

  - job_name: "core-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["core-service:8006"]

  - job_name: "ai-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["ai-service:8009"]

  - job_name: "auth-sidecar"
    metrics_path: /metrics
    static_configs:
      - targets: ["auth-sidecar:8010"]

  # ── API Gateway ──
  - job_name: "nginx"
    static_configs:
      - targets: ["nginx-exporter:9113"]

  # ── Infrastructure ──
  - job_name: "postgres-exporter"
    static_configs:
      - targets: ["postgres-exporter:9187"]

  - job_name: "redis-exporter"
    static_configs:
      - targets: ["redis-exporter:9121"]

  - job_name: "mongodb-exporter"
    static_configs:
      - targets: ["mongodb-exporter:9216"]

  - job_name: "rabbitmq"
    static_configs:
      - targets: ["rabbitmq:15692"]

  - job_name: "kafka-exporter"
    static_configs:
      - targets: ["kafka-exporter:9308"]
```

### 7B. Recording Rules — `monitoring/rules/recording_rules.yml`

Recording rules pre-compute expensive PromQL queries so dashboards load instantly instead of computing on every page load.

```yaml
groups:
  - name: smartcourse_recording_rules
    interval: 30s
    rules:
      # ── Request rate per service (5-minute window) ──
      - record: service:http_requests:rate5m
        expr: sum(rate(http_requests_total[5m])) by (handler, method, job)

      # ── Latency percentiles per service ──
      - record: service:http_request_duration_seconds:p50
        expr: histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, handler))

      - record: service:http_request_duration_seconds:p95
        expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, handler))

      - record: service:http_request_duration_seconds:p99
        expr: histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, handler))

      # ── Error rate per service ──
      - record: service:http_errors:rate5m
        expr: sum(rate(http_requests_total{status=~"5.."}[5m])) by (handler)

      # ── Redis cache hit ratio ──
      - record: redis:cache_hit_ratio
        expr: redis_keyspace_hits_total / (redis_keyspace_hits_total + redis_keyspace_misses_total)

      # ── Kafka consumer lag (total across all consumer groups) ──
      - record: kafka:consumer_lag:total
        expr: sum(kafka_consumergroup_lag) by (consumergroup, topic)

      # ── Container CPU usage rate ──
      - record: container:cpu_usage:rate5m
        expr: sum(rate(container_cpu_usage_seconds_total{name=~"smartcourse-.*"}[5m])) by (name)

      # ── Container memory usage percentage ──
      - record: container:memory_usage_ratio
        expr: container_memory_usage_bytes{name=~"smartcourse-.*"} / container_spec_memory_limit_bytes{name=~"smartcourse-.*"} > 0
```

### 7C. Alert Rules — `monitoring/rules/alert_rules.yml`

```yaml
groups:
  # ════════════════════════════════════════════════════
  #  SERVICE-LEVEL ALERTS
  # ════════════════════════════════════════════════════
  - name: smartcourse_service_alerts
    rules:

      # Any scrape target is unreachable
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "{{ $labels.job }} is DOWN"
          description: "Prometheus cannot reach {{ $labels.instance }} for job {{ $labels.job }}."

      # 5xx error rate exceeds 5% of total requests
      - alert: HighErrorRate
        expr: >
          sum(rate(http_requests_total{status=~"5.."}[5m])) by (job)
          / sum(rate(http_requests_total[5m])) by (job) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High 5xx error rate on {{ $labels.job }}"
          description: "{{ $labels.job }} has >5% error rate for the last 5 minutes."

      # P95 latency exceeds 2 seconds
      - alert: HighP95Latency
        expr: >
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job)
          ) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High P95 latency on {{ $labels.job }}"
          description: "P95 latency on {{ $labels.job }} exceeds 2 seconds."

  # ════════════════════════════════════════════════════
  #  INFRASTRUCTURE ALERTS
  # ════════════════════════════════════════════════════
  - name: smartcourse_infrastructure_alerts
    rules:

      # Container memory usage > 85% of its limit
      - alert: ContainerHighMemory
        expr: >
          (container_memory_usage_bytes{name=~"smartcourse-.*"}
          / container_spec_memory_limit_bytes{name=~"smartcourse-.*"}) > 0.85 > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Container {{ $labels.name }} memory > 85%"
          description: "Container {{ $labels.name }} is using more than 85% of its memory limit."

      # PostgreSQL connections approaching max (default 100)
      - alert: PostgresConnectionsHigh
        expr: pg_stat_activity_count > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "PostgreSQL connections above 80"
          description: "Default max_connections is 100. Current: {{ $value }}. Risk of connection exhaustion."

      # PostgreSQL unreachable
      - alert: PostgresDown
        expr: pg_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL is unreachable"
          description: "The postgres-exporter cannot connect to PostgreSQL."

      # Redis memory > 80% of maxmemory
      - alert: RedisHighMemory
        expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.8 > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Redis memory usage above 80%"
          description: "Redis is using {{ $value | humanizePercentage }} of maxmemory. Evictions likely."

      # Kafka consumer group falling behind
      - alert: KafkaConsumerLagHigh
        expr: kafka_consumergroup_lag > 1000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Kafka consumer group {{ $labels.consumergroup }} lag > 1000"
          description: "Topic {{ $labels.topic }} has {{ $value }} unprocessed messages."

      # RabbitMQ queue backing up
      - alert: RabbitMQQueueDepthHigh
        expr: rabbitmq_queue_messages > 500
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "RabbitMQ queue {{ $labels.queue }} has > 500 pending messages"
          description: "Queue depth: {{ $value }}. Workers may be stuck or underscaled."

      # Host disk > 80% full
      - alert: HostDiskSpaceHigh
        expr: >
          (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) > 0.8
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Host disk usage above 80%"
          description: "Root filesystem is {{ $value | humanizePercentage }} full."

      # Host CPU sustained above 85%
      - alert: HostCPUHigh
        expr: >
          100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Host CPU usage above 85%"
          description: "Sustained CPU usage: {{ $value }}%."
```

---

## 8. Phase 5 — AlertManager

### `monitoring/alertmanager.yml`

```yaml
global:
  resolve_timeout: 5m

# ── Routing Tree ──
route:
  group_by: ['alertname', 'severity']
  group_wait: 30s          # Wait before sending first notification for a group
  group_interval: 5m       # Wait before sending updates for a group
  repeat_interval: 4h      # Re-send if alert still firing
  receiver: 'default'

  routes:
    - match:
        severity: critical
      receiver: 'critical'
      group_wait: 10s        # Critical alerts notify faster
      repeat_interval: 1h

# ── Receivers ──
# For learning project: webhook stubs. In production, replace with:
#   slack_configs:
#     - api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'
#       channel: '#smartcourse-alerts'
#   OR
#   pagerduty_configs:
#     - service_key: 'YOUR_PAGERDUTY_KEY'
receivers:
  - name: 'default'
    webhook_configs:
      - url: 'http://alertmanager:9093/api/v2/alerts'
        send_resolved: true

  - name: 'critical'
    webhook_configs:
      - url: 'http://alertmanager:9093/api/v2/alerts'
        send_resolved: true

# ── Inhibition Rules ──
# If a service is DOWN, suppress its latency/error alerts (they're noise)
inhibit_rules:
  - source_match:
      alertname: 'ServiceDown'
    target_match_re:
      alertname: 'High.*'
    equal: ['job']
```

**Docker Compose service:**

```yaml
alertmanager:
  image: prom/alertmanager:v0.27.0
  container_name: smartcourse-alertmanager
  volumes:
    - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
  ports:
    - "9093:9093"
  command:
    - "--config.file=/etc/alertmanager/alertmanager.yml"
    - "--storage.path=/alertmanager"
  networks:
    - smartcourse-network
```

---

## 9. Phase 6 — Grafana Dashboard Provisioning

### 9A. Dashboard Provisioning Config

**File:** `monitoring/grafana/provisioning/dashboards/dashboards.yml`

```yaml
apiVersion: 1

providers:
  - name: 'SmartCourse'
    orgId: 1
    folder: 'SmartCourse'
    type: file
    disableDeletion: false
    editable: true
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards/json
      foldersFromFilesStructure: false
```

### 9B. Five Dashboards to Create

Place JSON files in `monitoring/grafana/provisioning/dashboards/json/`:

#### Dashboard 1: `smartcourse-overview.json` — System Overview (Landing Page)

**Purpose:** Single pane of glass. First thing you look at.

| Row | Panels | PromQL |
|-----|--------|--------|
| **Service Health** | Stat panels (UP/DOWN) for all targets | `up{job="user-service"}` etc. with value mappings: 1=green, 0=red |
| **Request Metrics** | Total req/s, total error/s, overall P95 | `sum(rate(http_requests_total[5m]))`, `sum(rate(http_requests_total{status=~"5.."}[5m]))`, `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))` |
| **Host Resources** | CPU %, Memory %, Disk % | `100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)`, `(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100`, `(1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100` |
| **Active Alerts** | Alert count + firing alerts list | `ALERTS{alertstate="firing"}` |

#### Dashboard 2: `smartcourse-services.json` — Application Services Deep Dive

**Purpose:** Per-service drill-down with a template variable.

**Template variable:** `$service` = `user-service, course-service, notification-service, core-service, ai-service, auth-sidecar`

| Panel | PromQL |
|-------|--------|
| Request rate by endpoint | `sum(rate(http_requests_total{job="$service"}[5m])) by (handler)` |
| P50 / P95 / P99 latency | `histogram_quantile(0.50/0.95/0.99, sum(rate(http_request_duration_seconds_bucket{job="$service"}[5m])) by (le, handler))` |
| Error breakdown by status | `sum(rate(http_requests_total{job="$service", status=~"[45].."}[5m])) by (status)` |
| In-progress requests | `http_requests_inprogress{job="$service"}` |
| Top 10 slowest endpoints | Table: `topk(10, histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="$service"}[5m])) by (le, handler)))` |

#### Dashboard 3: `smartcourse-containers.json` — Container Resources

**Purpose:** Resource usage per Docker container via cAdvisor.

| Panel | PromQL |
|-------|--------|
| CPU usage per container | `sum(rate(container_cpu_usage_seconds_total{name=~"smartcourse-.*"}[5m])) by (name)` |
| Memory usage per container | `container_memory_usage_bytes{name=~"smartcourse-.*"}` |
| Memory vs limit | `container_memory_usage_bytes{name=~"smartcourse-.*"} / container_spec_memory_limit_bytes{name=~"smartcourse-.*"}` |
| Network RX per container | `sum(rate(container_network_receive_bytes_total{name=~"smartcourse-.*"}[5m])) by (name)` |
| Network TX per container | `sum(rate(container_network_transmit_bytes_total{name=~"smartcourse-.*"}[5m])) by (name)` |
| Filesystem read/write | `sum(rate(container_fs_reads_bytes_total{name=~"smartcourse-.*"}[5m])) by (name)` |

#### Dashboard 4: `smartcourse-databases.json` — Databases & Cache

**Purpose:** Health of all data stores.

**PostgreSQL Section:**

| Panel | PromQL |
|-------|--------|
| Active connections | `pg_stat_activity_count` |
| Transaction rate | `rate(pg_stat_database_xact_commit{datname="smartcourse"}[5m])` |
| Tuple operations | `rate(pg_stat_database_tup_fetched[5m])`, `rate(pg_stat_database_tup_inserted[5m])`, etc. |
| Database size | `pg_database_size_bytes{datname="smartcourse"}` |
| Deadlocks | `rate(pg_stat_database_deadlocks[5m])` |

**Redis Section:**

| Panel | PromQL |
|-------|--------|
| Memory used vs max | `redis_memory_used_bytes` vs `redis_memory_max_bytes` |
| Connected clients | `redis_connected_clients` |
| Cache hit ratio | `redis_keyspace_hits_total / (redis_keyspace_hits_total + redis_keyspace_misses_total)` |
| Commands/sec | `rate(redis_commands_processed_total[5m])` |
| Evicted keys/sec | `rate(redis_evicted_keys_total[5m])` |

**MongoDB Section:**

| Panel | PromQL |
|-------|--------|
| Current connections | `mongodb_connections_current` |
| Operations/sec by type | `rate(mongodb_op_counters_total[5m])` grouped by `type` |
| Resident memory | `mongodb_memory_resident_megabytes` |

#### Dashboard 5: `smartcourse-messaging.json` — Kafka & RabbitMQ

**Purpose:** Event processing health.

**Kafka Section:**

| Panel | PromQL |
|-------|--------|
| Consumer lag by topic | `kafka_consumergroup_lag` grouped by `consumergroup, topic` |
| Messages in/sec by topic | `sum(rate(kafka_topic_partition_current_offset[5m])) by (topic)` |
| Broker count | `kafka_brokers` |

**RabbitMQ Section:**

| Panel | PromQL |
|-------|--------|
| Queue depth by queue | `rabbitmq_queue_messages` grouped by `queue` |
| Consumer count by queue | `rabbitmq_queue_consumers` grouped by `queue` |
| Publish rate | `rate(rabbitmq_channel_messages_published_total[5m])` |
| Deliver rate | `rate(rabbitmq_channel_messages_delivered_total[5m])` |

### 9C. How to Build the Dashboard JSON Files

**Option A — Use Community Templates (Recommended for infrastructure dashboards):**

Import these well-known Grafana dashboard IDs, export as JSON, adjust datasource UID to `"Prometheus"`:

| Dashboard | Grafana ID | URL |
|-----------|------------|-----|
| Node Exporter Full | `1860` | grafana.com/grafana/dashboards/1860 |
| cAdvisor | `14282` | grafana.com/grafana/dashboards/14282 |
| PostgreSQL | `9628` | grafana.com/grafana/dashboards/9628 |
| Redis | `11835` | grafana.com/grafana/dashboards/11835 |
| MongoDB | `2583` | grafana.com/grafana/dashboards/2583 |
| Kafka | `7589` | grafana.com/grafana/dashboards/7589 |
| RabbitMQ | `10991` | grafana.com/grafana/dashboards/10991 |

**Option B — Build in Grafana UI, then export:**

1. Create dashboards manually in Grafana using the PromQL from the tables above
2. Dashboard settings → JSON Model → Copy
3. Save to `monitoring/grafana/provisioning/dashboards/json/filename.json`
4. Now they auto-provision on every `docker compose up`

**Option C — Write JSON from scratch:** Each dashboard is a Grafana JSON model (~200-500 lines) with panels containing `type`, `datasource`, `targets[].expr`, `gridPos`, etc. This is tedious but gives full control.

> **Recommendation:** Use Option A for infra dashboards, Option B for the custom Overview and Services dashboards.

---

## 10. Phase 7 — Enhanced FastAPI Metrics

### Current State (All 5 Services)

```python
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

This uses bare defaults — it instruments everything including `/health` and `/metrics` endpoints (noise), doesn't group status codes, and doesn't track in-progress requests.

### Enhanced Configuration

Replace in each service's `main.py`:

```python
from prometheus_fastapi_instrumentator import Instrumentator

instrumentator = Instrumentator(
    should_group_status_codes=False,         # Report 401, 403, 500 separately (not just "4xx", "5xx")
    should_ignore_untemplated=True,          # Ignore routes not in OpenAPI schema
    should_respect_env_var=False,            # Always enable (don't depend on env var)
    excluded_handlers=["/health", "/metrics"],  # Don't pollute metrics with infra endpoints
    should_instrument_requests_inprogress=True,  # Track concurrent request count
    inprogress_name="smartcourse_inprogress_requests",
    inprogress_labels=True,
)
instrumentator.instrument(app).expose(app, endpoint="/metrics")
```

### Optional: Custom Business Metrics

Define these in a shared location or per-service:

```python
from prometheus_client import Histogram, Counter

# Time spent calling external dependencies (DB, Redis, Kafka, etc.)
DEPENDENCY_LATENCY = Histogram(
    "smartcourse_dependency_duration_seconds",
    "Time spent calling external dependencies",
    ["service", "dependency", "operation"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# Business-level event counter
BUSINESS_EVENTS = Counter(
    "smartcourse_business_events_total",
    "Business-level event counter",
    ["service", "event_type"],
)
```

**Usage examples:**

```python
# In user-service registration handler:
BUSINESS_EVENTS.labels(service="user-service", event_type="user_registered").inc()

# In course-service enrollment handler:
BUSINESS_EVENTS.labels(service="course-service", event_type="course_enrolled").inc()

# Timing a database call:
with DEPENDENCY_LATENCY.labels(service="user-service", dependency="postgres", operation="get_user").time():
    user = await db.get_user(user_id)
```

> This is incremental — the Instrumentator config change deploys immediately, custom metric calls are added per-handler over time.

---

## 11. Docker Compose — Complete Changes

### New Services to Add

```yaml
  # ═══════════════════════════════════════════════════════════════
  #  OBSERVABILITY — Exporters & Alerting
  # ═══════════════════════════════════════════════════════════════

  cadvisor:
    image: gcr.io/cadvisor/cadvisor:v0.49.1
    container_name: smartcourse-cadvisor
    privileged: true
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
    ports:
      - "8085:8080"
    networks:
      - smartcourse-network

  node-exporter:
    image: prom/node-exporter:v1.7.0
    container_name: smartcourse-node-exporter
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - "--path.procfs=/host/proc"
      - "--path.sysfs=/host/sys"
      - "--path.rootfs=/rootfs"
      - "--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)"
    ports:
      - "9100:9100"
    networks:
      - smartcourse-network

  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:v0.15.0
    container_name: smartcourse-postgres-exporter
    environment:
      DATA_SOURCE_NAME: "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}?sslmode=disable"
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - smartcourse-network

  redis-exporter:
    image: oliver006/redis_exporter:v1.58.0
    container_name: smartcourse-redis-exporter
    environment:
      REDIS_ADDR: "redis://redis:6379"
      REDIS_PASSWORD: "${REDIS_PASSWORD}"
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - smartcourse-network

  mongodb-exporter:
    image: percona/mongodb_exporter:0.40.0
    container_name: smartcourse-mongodb-exporter
    command:
      - "--mongodb.uri=mongodb://${MONGO_USER}:${MONGO_PASSWORD}@mongodb:27017/admin"
      - "--collect-all"
      - "--compatible-mode"
    depends_on:
      mongodb:
        condition: service_healthy
    networks:
      - smartcourse-network

  kafka-exporter:
    image: danielqsj/kafka-exporter:v1.7.0
    container_name: smartcourse-kafka-exporter
    command:
      - "--kafka.server=kafka:29092"
      - "--topic.filter=.*"
      - "--group.filter=.*"
    depends_on:
      kafka:
        condition: service_healthy
    networks:
      - smartcourse-network

  nginx-exporter:
    image: nginx/nginx-prometheus-exporter:1.1
    container_name: smartcourse-nginx-exporter
    command:
      - "-nginx.scrape-uri=http://api-gateway:8000/stub_status"
    depends_on:
      - api-gateway
    networks:
      - smartcourse-network

  alertmanager:
    image: prom/alertmanager:v0.27.0
    container_name: smartcourse-alertmanager
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    ports:
      - "9093:9093"
    command:
      - "--config.file=/etc/alertmanager/alertmanager.yml"
      - "--storage.path=/alertmanager"
    networks:
      - smartcourse-network
```

### Existing Services to Modify

**prometheus** — add rules volume mount:

```yaml
prometheus:
  image: prom/prometheus:v2.51.0
  container_name: smartcourse-prometheus
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    - ./monitoring/rules:/etc/prometheus/rules:ro          # ← ADD THIS
    - prometheus_data:/prometheus
  # ... rest unchanged ...
```

**rabbitmq** — add enabled_plugins mount:

```yaml
rabbitmq:
  image: rabbitmq:3.13-management
  # ... existing config unchanged ...
  volumes:
    - rabbitmq_data:/var/lib/rabbitmq
    - ./monitoring/rabbitmq/enabled_plugins:/etc/rabbitmq/enabled_plugins:ro  # ← ADD THIS
```

---

## 12. File Tree Summary

### New Files to Create

```
monitoring/
├── prometheus.yml                              # MODIFY (fix ports, add targets, rules, alerting)
├── alertmanager.yml                            # CREATE
├── rules/
│   ├── recording_rules.yml                     # CREATE
│   └── alert_rules.yml                         # CREATE
├── rabbitmq/
│   └── enabled_plugins                         # CREATE
└── grafana/
    └── provisioning/
        ├── datasources/
        │   └── prometheus.yaml                 # EXISTS — no change
        └── dashboards/
            ├── dashboards.yml                  # CREATE (provisioning config)
            └── json/
                ├── smartcourse-overview.json    # CREATE
                ├── smartcourse-services.json    # CREATE
                ├── smartcourse-containers.json  # CREATE
                ├── smartcourse-databases.json   # CREATE
                └── smartcourse-messaging.json   # CREATE

services/api-gateway/
├── nginx.conf                                  # MODIFY (add stub_status)
├── Dockerfile.sidecar                          # MODIFY (add prometheus dep)
└── auth-sidecar.py                             # MODIFY (add instrumentator)
```

### Files to Modify

| File | Change |
|------|--------|
| `docker-compose.yml` | Add 8 new services, modify prometheus + rabbitmq volumes |
| `monitoring/prometheus.yml` | Complete rewrite (fix ports, add 12 new targets, rules, alerting) |
| `services/api-gateway/nginx.conf` | Add `stub_status` location block |
| `services/api-gateway/Dockerfile.sidecar` | Add `prometheus-fastapi-instrumentator` to pip install |
| `services/api-gateway/auth-sidecar.py` | Add Instrumentator import and setup |
| 5x FastAPI `main.py` files | Enhanced Instrumentator config (optional, incremental) |

---

## 13. Verification Checklist

### Step 1: Start Everything

```bash
docker compose up -d
```

### Step 2: Verify All Targets Are UP

Open http://localhost:9090/targets and confirm all 17 targets show `UP`:

- [ ] prometheus
- [ ] node-exporter
- [ ] cadvisor
- [ ] user-service
- [ ] course-service
- [ ] notification-service
- [ ] core-service
- [ ] ai-service
- [ ] auth-sidecar
- [ ] nginx
- [ ] postgres-exporter
- [ ] redis-exporter
- [ ] mongodb-exporter
- [ ] rabbitmq
- [ ] kafka-exporter

### Step 3: Verify Alert Rules Loaded

Open http://localhost:9090/alerts:

- [ ] `smartcourse_service_alerts` group visible with 3 rules
- [ ] `smartcourse_infrastructure_alerts` group visible with 8 rules
- [ ] No alerts firing on a healthy system

### Step 4: Verify AlertManager

Open http://localhost:9093:

- [ ] AlertManager UI loads
- [ ] No alerts showing (healthy system)

### Step 5: Verify Grafana Dashboards

Open http://localhost:3000 (admin/smartcourse):

- [ ] "SmartCourse" folder appears in sidebar
- [ ] 5 dashboards visible
- [ ] Overview dashboard shows green service health, live request metrics
- [ ] Container dashboard shows CPU/memory per container
- [ ] Database dashboard shows PostgreSQL connections, Redis memory

### Step 6: Test Alerting End-to-End

```bash
# Stop a service
docker compose stop user-service

# Wait ~1 minute, then check:
# Prometheus: http://localhost:9090/alerts → ServiceDown should be FIRING
# AlertManager: http://localhost:9093 → Alert should appear

# Restart
docker compose start user-service

# Wait ~1 minute, alert should resolve
```

### Step 7: Test Container Metrics

```bash
# Simulate CPU load on a service (optional)
docker exec smartcourse-user-service python -c "
import time
start = time.time()
while time.time() - start < 30:
    sum(range(1000000))
"

# Check cAdvisor dashboard — user-service CPU should spike
```

---

## 14. macOS / Docker Desktop Notes

| Component | Behavior on macOS |
|-----------|-------------------|
| **cAdvisor** | Reports metrics for the Docker Desktop Linux VM, not the Mac host. Container-level metrics (CPU, memory per container) work correctly. Some filesystem metrics may be limited. |
| **node-exporter** | Reports Linux VM metrics. This is actually useful — the VM is what your containers share. On a Linux production host, this would report real host metrics. |
| **Docker socket** | `/var/run/docker.sock` is available in Docker Desktop. cAdvisor will work. |
| **Resource limits** | Container memory limits (`container_spec_memory_limit_bytes`) only work if you set `mem_limit` in docker-compose. Without limits, the ratio alerts won't fire. Consider adding `mem_limit` to services for production. |

### Recommended: Add Memory Limits for Container Alerts

To make `ContainerHighMemory` alerts work, add `mem_limit` to your services:

```yaml
user-service:
  # ... existing config ...
  mem_limit: 512m

course-service:
  # ... existing config ...
  mem_limit: 512m

ai-service:
  # ... existing config ...
  mem_limit: 1g   # AI service likely needs more

notification-service:
  # ... existing config ...
  mem_limit: 256m

core-service:
  # ... existing config ...
  mem_limit: 512m
```

---

## Summary of Access Points After Implementation

| Service | URL | Purpose |
|---------|-----|---------|
| **Grafana** | http://localhost:3000 | Dashboards (admin/smartcourse) |
| **Prometheus** | http://localhost:9090 | Metrics, targets, alerts, PromQL explorer |
| **AlertManager** | http://localhost:9093 | Alert routing, silencing, grouping |
| **cAdvisor** | http://localhost:8085 | Raw container metrics UI |
| **Node Exporter** | http://localhost:9100/metrics | Raw host metrics |
| **RabbitMQ** | http://localhost:15672 | Management UI (existing) |
| **Temporal** | http://localhost:8080 | Workflow UI (existing) |
