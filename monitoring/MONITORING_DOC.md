# SmartCourse Monitoring — Understanding Doc

A full walkthrough of how Prometheus + Grafana are set up, what data they collect, and where everything lives.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prometheus — How It Works](#2-prometheus--how-it-works)
3. [Application Metrics — What the Services Expose](#3-application-metrics--what-the-services-expose)
4. [Infrastructure Exporters — Everything Else](#4-infrastructure-exporters--everything-else)
5. [Grafana — Dashboards & Data Source](#5-grafana--dashboards--data-source)
6. [Alerting — Rules & Routing](#6-alerting--rules--routing)
7. [Recording Rules — Pre-aggregated Metrics](#7-recording-rules--pre-aggregated-metrics)
8. [Data Storage & Retention](#8-data-storage--retention)
9. [Networking — How Services Connect](#9-networking--how-services-connect)
10. [Quick Reference](#10-quick-reference)

---

## 1. Architecture Overview

```
Your App Services ──┐
                    │  expose /metrics
Infrastructure ─────┤  (HTTP endpoint)
Exporters      ─────┘
                         ↓ scrape every 15s
                    Prometheus (9090)
                         │
                         ├──► evaluates alert rules
                         │         ↓
                         │    Alertmanager (9093)
                         │
                    Grafana (3000)
                         │  queries Prometheus
                         └──► renders dashboards
```

**The key idea:** Every service and database exposes a `/metrics` HTTP endpoint. Prometheus polls all of them every 15 seconds and stores the data. Grafana reads from Prometheus to draw dashboards.

---

## 2. Prometheus — How It Works

**Config file:** `monitoring/prometheus.yml`

### Global settings

```yaml
global:
  scrape_interval: 15s       # poll every target every 15 seconds
  evaluation_interval: 15s   # re-evaluate alert/recording rules every 15s
```

### Scrape targets (18 jobs total)

Prometheus is told about each target in `scrape_configs`. Each entry is called a "job".

**Application services:**

| Job name | Target (internal DNS) | What it monitors |
|---|---|---|
| `user-service` | `user-service:8001/metrics` | User auth, profiles |
| `course-service` | `course-service:8002/metrics` | Courses, enrollment |
| `notification-service` | `notification-service:8005/metrics` | Notifications |
| `core-service` | `core-service:8006/metrics` | Core business logic |
| `analytics-service` | `analytics-service:8007/metrics` | Analytics |
| `ai-service` | `ai-service:8009/metrics` | AI/LLM features |
| `auth-sidecar` | `auth-sidecar:8010/metrics` | Auth middleware |

**Infrastructure exporters:**

| Job name | Target | What it monitors |
|---|---|---|
| `prometheus` | `localhost:9090` | Prometheus itself |
| `node-exporter` | `node-exporter:9100` | Host CPU, memory, disk |
| `cadvisor` | `cadvisor:8080` | Docker container resources |
| `postgres-exporter` | `postgres-exporter:9187` | PostgreSQL |
| `redis-exporter` | `redis-exporter:9121` | Redis |
| `mongodb-exporter` | `mongodb-exporter:9216` | MongoDB |
| `rabbitmq` | `rabbitmq:15692` | RabbitMQ queues |
| `kafka-exporter` | `kafka-exporter:9308` | Kafka topics/consumers |
| `nginx` | `nginx-exporter:9113` | Nginx API gateway |

**How Prometheus stores data:** Every 15 seconds it hits each `/metrics` endpoint, parses the response (Prometheus text format), and writes a time-series entry to its local TSDB (time-series database) on disk.

---

## 3. Application Metrics — What the Services Expose

**How metrics are added to the FastAPI services:**

All 7 services use the `prometheus-fastapi-instrumentator` library. It hooks into FastAPI and automatically records HTTP metrics for every request.

**Example from any service's `main.py`:**
```python
from prometheus_fastapi_instrumentator import Instrumentator

instrumentator = Instrumentator(
    should_group_status_codes=False,       # track 200, 404, 500 separately (not just 2xx, 4xx)
    should_ignore_untemplated=True,        # ignore dynamic paths like /users/abc123
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/health", "/metrics"],  # don't track these endpoints
    inprogress_name="smartcourse_inprogress_requests",
)
instrumentator.instrument(app).expose(app)
```

**Metrics this produces:**

| Metric | Type | What it measures |
|---|---|---|
| `http_requests_total` | Counter | Total requests, labeled by status code, method, handler path |
| `http_request_duration_seconds` | Histogram | Request latency (used for p50/p95/p99 calculations) |
| `smartcourse_inprogress_requests` | Gauge | Currently in-flight requests |

**Label dimensions:** Each metric has labels so you can filter/group queries:
- `job` — which service (e.g. `user-service`)
- `handler` — which endpoint (e.g. `/users/me`)
- `method` — HTTP method (GET, POST, etc.)
- `status` — HTTP status code (200, 422, 500, etc.)

**Example metric line (what Prometheus actually receives):**
```
http_requests_total{job="user-service", handler="/users/me", method="GET", status="200"} 1247
http_request_duration_seconds_bucket{job="course-service", handler="/courses", le="0.5"} 892
```

---

## 4. Infrastructure Exporters — Everything Else

These are standalone processes (not part of your app) that translate database/host stats into Prometheus metrics.

### Node Exporter (host machine metrics)
**Port:** 9100 | **Source of truth:** `/proc` and `/sys` on the host

Key metrics:
- `node_cpu_seconds_total{mode="idle|user|system"}` — CPU usage
- `node_memory_MemAvailable_bytes` / `node_memory_MemTotal_bytes` — RAM
- `node_filesystem_avail_bytes{mountpoint="/"}` — disk space

### cAdvisor (container metrics)
**Port:** 8080 | **Source of truth:** Docker daemon

Key metrics:
- `container_cpu_usage_seconds_total{name="smartcourse-..."}` — per-container CPU
- `container_memory_usage_bytes{name="smartcourse-..."}` — per-container memory
- `container_network_receive_bytes_total` — network I/O

### PostgreSQL Exporter
**Port:** 9187 | **Source of truth:** PostgreSQL `pg_stat_*` views

Key metrics:
- `pg_stat_activity_count` — active connections (alert fires at > 80, max is 100)
- `pg_stat_database_xact_commit` — transaction commit rate
- `pg_database_size_bytes{datname="smartcourse"}` — database size
- `pg_up` — 0 if the exporter can't connect (triggers critical alert)

### Redis Exporter
**Port:** 9121 | **Source of truth:** Redis `INFO` command

Key metrics:
- `redis_memory_used_bytes` / `redis_memory_max_bytes` — memory usage
- `redis_connected_clients` — active connections
- `redis_keyspace_hits_total` / `redis_keyspace_misses_total` — cache hit ratio

### MongoDB Exporter
**Port:** 9216 | **Source of truth:** MongoDB `serverStatus`

Key metrics:
- `mongodb_op_counters_total{type="insert|update|delete|find"}` — operation rates

### RabbitMQ (built-in Prometheus plugin)
**Port:** 15692 | **No separate exporter needed** — RabbitMQ has a native Prometheus endpoint

Enabled via: `monitoring/rabbitmq/enabled_plugins`
```
[rabbitmq_management, rabbitmq_prometheus].
```

Key metrics:
- `rabbitmq_queue_messages{queue="..."}` — messages waiting in queue
- `rabbitmq_queue_consumers{queue="..."}` — consumers per queue
- `rabbitmq_channel_messages_published_total` — publish rate

### Kafka Exporter
**Port:** 9308 | **Source of truth:** Kafka broker API

Key metrics:
- `kafka_consumergroup_lag{consumergroup="...", topic="..."}` — how far behind consumers are
- `kafka_topic_partition_current_offset` — latest offset per topic/partition

### Nginx Exporter
**Port:** 9113 | **Source of truth:** Nginx stub_status endpoint

Key metrics:
- Active connections, requests/sec, reading/writing/waiting

---

## 5. Grafana — Dashboards & Data Source

**Config lives in:** `monitoring/grafana/provisioning/`

Grafana uses "provisioning" — instead of clicking through the UI to set up data sources and dashboards, everything is defined as YAML/JSON files that load automatically on startup.

### Data source

**File:** `monitoring/grafana/provisioning/datasources/prometheus.yaml`

```yaml
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090   # Grafana → Prometheus (internal Docker network)
    isDefault: true
    access: proxy                 # Grafana server makes the request, not your browser
```

This means: when you open a Grafana dashboard, your browser talks to Grafana (port 3000), and Grafana talks to Prometheus (port 9090) internally. Prometheus port is never exposed to your browser.

### Dashboards

**Dashboard JSONs:** `monitoring/grafana/provisioning/dashboards/json/`

**Dashboard provisioning config:** `monitoring/grafana/provisioning/dashboards/dashboards.yml`
- Grafana folder: "SmartCourse"
- Update interval: 30 seconds (re-reads JSON files from disk)

**4 dashboards:**

#### 1. SmartCourse Overview (`smartcourse-overview.json`)
Big-picture health at a glance. Refreshes every 30s, default time range: last 6 hours.

Panels:
- Service health status for all 6 services (green/red based on `up` metric)
- Total requests/sec across all services
- 5xx error rate
- Overall P95 latency
- Host CPU %
- Host memory %
- Active firing alerts

#### 2. SmartCourse Services (`smartcourse-services.json`)
Deep-dive into HTTP traffic per service.

Panels:
- Request rate by endpoint (broken down by handler path)
- Latency percentiles (p50, p95, p99) per endpoint
- Error breakdown by HTTP status code
- In-progress requests count
- Top 10 slowest endpoints

Has a **service filter dropdown** — select which service to inspect (user-service, course-service, etc.)

#### 3. SmartCourse Databases (`smartcourse-databases.json`)
Database health panels:

- **PostgreSQL:** Active connections by state, transaction commit rate, DB size
- **Redis:** Memory used vs max, connected clients, hit ratio, commands/sec, evictions/sec
- **MongoDB:** Operations/sec (insert, update, delete, find)

#### 4. SmartCourse Messaging (`smartcourse-messaging.json`)
Message queue health panels:

- **Kafka:** Consumer group lag by group+topic, messages in per topic, broker count
- **RabbitMQ:** Queue depth per queue, consumers per queue, publish/delivery rates

---

## 6. Alerting — Rules & Routing

**Alert rules:** `monitoring/rules/alert_rules.yml`
**Alertmanager config:** `monitoring/alertmanager.yml`
**Alertmanager port:** 9093

### How alerting works

1. Prometheus evaluates `alert_rules.yml` every 15 seconds
2. If a rule's expression is true for longer than its `for` duration → alert fires
3. Prometheus sends the alert to Alertmanager
4. Alertmanager deduplicates, groups, and routes alerts to receivers
5. Currently receivers are webhook endpoints (pointing back at Alertmanager's own API — placeholders for real integrations like PagerDuty/Slack)

### Alert rules (11 total)

**Group A: Application alerts**

| Alert | Severity | Condition | Duration |
|---|---|---|---|
| `ServiceDown` | critical | `up == 0` | 1 min |
| `HighErrorRate` | warning | 5xx rate > 5% over 5m | 5 min |
| `HighP95Latency` | warning | P95 latency > 2 seconds | 5 min |

**Group B: Infrastructure alerts**

| Alert | Severity | Condition | Duration |
|---|---|---|---|
| `ContainerHighMemory` | warning | container memory > 85% of limit | 5 min |
| `PostgresConnectionsHigh` | warning | active connections > 80 (out of 100 max) | 5 min |
| `PostgresDown` | critical | `pg_up == 0` | 1 min |
| `RedisHighMemory` | warning | Redis memory > 80% of maxmemory | 5 min |
| `KafkaConsumerLagHigh` | warning | consumer lag > 1000 messages | 10 min |
| `RabbitMQQueueDepthHigh` | warning | queue depth > 500 messages | 10 min |
| `HostDiskSpaceHigh` | warning | root filesystem > 80% full | 10 min |
| `HostCPUHigh` | warning | CPU usage > 85% | 10 min |

### Alert routing

```
All alerts
    │
    ├── severity=critical
    │       group_wait: 10s (fire quickly)
    │       repeat_interval: 1h
    │       receiver: critical-webhook
    │
    └── everything else
            group_wait: 30s
            repeat_interval: 4h
            receiver: default-webhook
```

**Inhibition rules:** If `ServiceDown` fires for a job, all warning-level alerts for that same job are suppressed. Prevents alert spam when a service goes down (you already know it's down).

---

## 7. Recording Rules — Pre-aggregated Metrics

**File:** `monitoring/rules/recording_rules.yml`
**Evaluation interval:** 30 seconds

Recording rules pre-compute expensive queries and store the result as a new metric. This makes dashboard queries fast (no heavy computation at dashboard load time).

| Recorded metric | What it computes |
|---|---|
| `service:http_requests:rate5m` | 5-minute request rate, per job/method/handler |
| `service:http_request_duration_seconds:p50` | Median latency per service |
| `service:http_request_duration_seconds:p95` | 95th percentile latency per service |
| `service:http_request_duration_seconds:p99` | 99th percentile latency per service |
| `service:http_errors:rate5m` | 5xx error rate per handler |
| `redis:cache_hit_ratio` | Redis hit/(hit+miss) ratio |
| `kafka:consumer_lag:total` | Total lag aggregated by consumer group + topic |
| `container:cpu_usage:rate5m` | CPU rate for smartcourse-* containers |
| `container:memory_usage_ratio` | Memory % for smartcourse-* containers |

Dashboards query these `service:*` and `container:*` metrics rather than re-computing from raw data each time.

---

## 8. Data Storage & Retention

### Prometheus data

- **Docker volume:** `prometheus_data`
- **Mounted at:** `/prometheus` inside the container
- **Retention:** 15 days (`--storage.tsdb.retention.time=15d` flag)
- **Format:** Prometheus TSDB (custom compressed binary format)
- **What's stored:** Every scraped metric value with its timestamp and labels

After 15 days, old data is automatically deleted.

### Grafana data

- **Docker volume:** `grafana_data`
- **Mounted at:** `/var/lib/grafana`
- **What's stored:** Grafana's own SQLite database (users, sessions, dashboard edits made via UI)
- **Note:** Dashboard definitions are in provisioning files, so they survive even if this volume is deleted

Both volumes persist across `docker-compose down` / `docker-compose up` cycles. To fully wipe data: `docker volume rm prometheus_data grafana_data`.

---

## 9. Networking — How Services Connect

All containers are on the `smartcourse-network` Docker bridge network. Docker provides DNS — container names resolve to their internal IPs.

**Data flow:**

```
[Browser]
    │
    ├── localhost:3000 → Grafana container
    │       └── http://prometheus:9090  (internal, queries PromQL)
    │
    └── localhost:9090 → Prometheus container (direct access for debugging)
            │
            ├── scrapes user-service:8001/metrics
            ├── scrapes course-service:8002/metrics
            ├── scrapes notification-service:8005/metrics
            ├── scrapes core-service:8006/metrics
            ├── scrapes analytics-service:8007/metrics
            ├── scrapes ai-service:8009/metrics
            ├── scrapes auth-sidecar:8010/metrics
            │
            ├── scrapes node-exporter:9100/metrics
            ├── scrapes cadvisor:8080/metrics
            ├── scrapes postgres-exporter:9187/metrics
            ├── scrapes redis-exporter:9121/metrics
            ├── scrapes mongodb-exporter:9216/metrics
            ├── scrapes rabbitmq:15692/metrics
            ├── scrapes kafka-exporter:9308/metrics
            └── scrapes nginx-exporter:9113/metrics
```

**Ports exposed to host (for your browser):**

| Service | Host port | Purpose |
|---|---|---|
| Grafana | 3000 | Main monitoring UI |
| Prometheus | 9090 | Query UI, targets page |
| Alertmanager | 9093 | Alert management UI |

Exporter ports are **not** exposed to the host — only accessible container-to-container.

---

## 10. Quick Reference

### Key file locations

| What | Where |
|---|---|
| Prometheus config | `monitoring/prometheus.yml` |
| Alert rules | `monitoring/rules/alert_rules.yml` |
| Recording rules | `monitoring/rules/recording_rules.yml` |
| Alertmanager config | `monitoring/alertmanager.yml` |
| Grafana data source | `monitoring/grafana/provisioning/datasources/prometheus.yaml` |
| Dashboard configs | `monitoring/grafana/provisioning/dashboards/` |
| Dashboard JSONs | `monitoring/grafana/provisioning/dashboards/json/` |
| RabbitMQ plugin config | `monitoring/rabbitmq/enabled_plugins` |

### Grafana login

- URL: `http://localhost:3000`
- Username: `admin`
- Password: `smartcourse`

### Useful Prometheus queries to run manually

```promql
# Is a service up?
up{job="user-service"}

# Request rate for user-service over last 5 min
rate(http_requests_total{job="user-service"}[5m])

# P95 latency for course-service
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job="course-service"}[5m]))

# 5xx error rate percentage
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) * 100

# Kafka consumer lag
kafka_consumergroup_lag

# Redis memory usage %
redis_memory_used_bytes / redis_memory_max_bytes * 100
```
