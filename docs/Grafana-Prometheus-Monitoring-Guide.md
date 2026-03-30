# Grafana + Prometheus Monitoring Guide for SmartCourse

---

## 1. What is Prometheus & Why Do You Need It?

Prometheus is a **metrics collection and storage system** — a database built specifically for time-series data (numbers that change over time like request counts, latency, errors).

**How it works:**
```
Your FastAPI services expose metrics at /metrics endpoint (plain text)
        │
        ▼
Prometheus PULLS (scrapes) those numbers every 15 seconds
        │
        ▼
Stores them in its time-series database with timestamps
        │
        ▼
You query them using PromQL (Prometheus Query Language)
```

**Types of metrics it collects:**
- **Counters** — only go up: total requests served, total errors
- **Gauges** — go up and down: current CPU usage, active connections
- **Histograms** — distributions: how many requests took <100ms, <500ms, etc.

**Example `/metrics` output (plain text):**
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET", endpoint="/api/v1/courses", status="200"} 1547
http_requests_total{method="POST", endpoint="/api/v1/users", status="201"} 89

# HELP http_request_duration_seconds Request latency
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{endpoint="/api/v1/courses", le="0.1"} 1200
```

---

## 2. What is Grafana?

Grafana is a **visualization and dashboarding tool**. It connects to data sources (like Prometheus) and lets you build dashboards with graphs, gauges, tables, and alerts.

**"Can I use Grafana without Prometheus?"** — No. Grafana is just a visualization layer, it needs a data source. Prometheus is the standard choice for microservice metrics.

**Why not just use Prometheus UI?**
Prometheus has a basic query UI, but Grafana gives you: beautiful dashboards, alerts (email/Slack), multiple data sources, team sharing, and thousands of pre-built community dashboard templates.

---

## 3. How They Work Together in Your Project

```
┌──────────────────────────────────────────────────────────────────┐
│                 DOCKER NETWORK (smartcourse-network)             │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐          │
│  │ user-service  │  │course-service│  │  ai-service    │         │
│  │  /metrics  ◄──┼──┼──────┐       │  │  /metrics  ◄──┼──┐      │
│  └──────────────┘  └──────┼────────┘  └───────────────┘  │      │
│                           │                               │      │
│  ┌────────────────────────┼───────────────────────────────┼────┐ │
│  │      PROMETHEUS :9090  │    (scrapes /metrics)         │    │ │
│  │                        ◄───────────────────────────────┘    │ │
│  │  Stores time-series data with timestamps                    │ │
│  └────────┬────────────────────────────────────────────────────┘ │
│           │ PromQL queries                                       │
│           ▼                                                      │
│  ┌─────────────────────────┐                                     │
│  │     GRAFANA :3000       │◄── You open http://localhost:3000   │
│  │  Dashboards & Alerts    │                                     │
│  └─────────────────────────┘                                     │
└──────────────────────────────────────────────────────────────────┘
```

**The flow:**
1. Your FastAPI apps use `prometheus-fastapi-instrumentator` library to auto-expose `/metrics`
2. Prometheus scrapes each service's `/metrics` every 15 seconds
3. Grafana connects to Prometheus as a "data source"
4. You build dashboards in Grafana that query Prometheus using PromQL

---

## 4. Step-by-Step Implementation

### Step 1: Create the directory structure

```bash
mkdir -p monitoring/grafana/provisioning/datasources
```

### Step 2: Create `monitoring/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]

  # Use Docker service names (NOT localhost) — Docker DNS resolves these
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
      - targets: ["notification-service:8003"]

  - job_name: "core-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["core-service:8006"]

  - job_name: "ai-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["ai-service:8005"]
```

> **Why Docker service names?** Inside Docker's bridge network, containers find each other by the service name defined in `docker-compose.yml`. So `user-service:8001` means "the container named user-service on its internal port 8001".

### Step 3: Create `monitoring/grafana/provisioning/datasources/prometheus.yml`

This auto-connects Grafana to Prometheus on startup (no manual setup needed):

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

### Step 4: Add to `docker-compose.yml`

Add these two services **before** the `networks:` section:

```yaml
  # ═══════════════════════════════════════════════════════════════
  #  MONITORING — Prometheus + Grafana
  # ═══════════════════════════════════════════════════════════════

  prometheus:
    image: prom/prometheus:v2.51.0
    container_name: smartcourse-prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=15d"
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:9090/-/healthy"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - smartcourse-network

  grafana:
    image: grafana/grafana:10.4.1
    container_name: smartcourse-grafana
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: smartcourse
      GF_USERS_ALLOW_SIGN_UP: "false"
    depends_on:
      prometheus:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:3000/api/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - smartcourse-network
```

And add to the `volumes:` section at the bottom:

```yaml
volumes:
  postgres_data:
  redis_data:
  mongodb_data:
  rabbitmq_data:
  qdrant_data:
  prometheus_data:    # ADD THIS
  grafana_data:       # ADD THIS
```

### Step 5: Add metrics to each FastAPI service

**Install the library** — add to each service's `pyproject.toml` under `dependencies`:

```toml
"prometheus-fastapi-instrumentator>=7.0.2",
```

**Add 2 lines** in each service's main app file (where `app = FastAPI()` is):

```python
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(...)

# Add this ONE line after creating the app:
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

That's it! This automatically tracks:
- Total requests per endpoint, method, and status code
- Request duration (latency histogram)
- Requests currently in progress
- Request/response sizes

### Step 6: Start and verify

```bash
docker-compose up -d prometheus grafana

# Verify Prometheus is running and scraping:
open http://localhost:9090/targets     # All services should show "UP"

# Open Grafana:
open http://localhost:3000
# Login: admin / smartcourse
```

---

## 5. Building Your First Dashboard

After logging into Grafana at `http://localhost:3000`:

1. Click **"+"** (top right) -> **"New Dashboard"**
2. Click **"Add visualization"**
3. Select **"Prometheus"** as data source
4. Use these PromQL queries:

```promql
# Request rate (requests per second) across all services
rate(http_requests_total[5m])

# Average response time per service
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])

# Error rate (5xx responses only)
rate(http_requests_total{status=~"5.."}[5m])

# Requests currently being processed
http_requests_in_progress
```

### PromQL Cheat Sheet

```promql
rate(metric[5m])                                    # Per-second rate over 5 min
sum(rate(http_requests_total[5m]))                  # Total req/sec all services
sum(rate(http_requests_total[5m])) by (handler)     # Grouped by endpoint
http_requests_total{status="500"}                   # Filter: only 500 errors
http_requests_total{handler=~"/api/v1/.*"}          # Filter: regex match
```

---

## 6. Docker Compose vs Kubernetes

### Quick Answer

**Docker Compose** = run multiple containers on **one machine**, simple YAML, great for dev/small deploys.
**Kubernetes (K8s)** = orchestrate containers across **many machines**, auto-scaling, self-healing, production-grade.

### Comparison

```
┌─────────────────────┬──────────────────────┬──────────────────────────┐
│     Feature         │   Docker Compose     │      Kubernetes          │
├─────────────────────┼──────────────────────┼──────────────────────────┤
│ Runs on             │ Single machine       │ Cluster (many machines)  │
│ Complexity          │ 1 YAML file          │ Many YAMLs, steep curve  │
│ Scaling             │ Manual (replicas: 3) │ Auto-scale on CPU/memory │
│ Self-healing        │ restart: on-failure  │ Reschedule to new node   │
│ Load balancing      │ Basic round-robin    │ Built-in + Ingress       │
│ Rolling updates     │ No (restarts all)    │ Zero-downtime deploys    │
│ Service discovery   │ Docker DNS           │ DNS + Service objects    │
│ Secrets             │ .env files           │ Kubernetes Secrets       │
│ Best for            │ Dev, learning, small │ Production at scale      │
│ Setup time          │ Minutes              │ Hours to days            │
│ Cost                │ Free (just Docker)   │ Cluster infra $$$        │
└─────────────────────┴──────────────────────┴──────────────────────────┘
```

### Why Docker Compose matters

Docker Compose is important because it lets you:
- **Define your entire stack as code** — one `docker-compose.yml` describes all 15+ services
- **One command to start everything** — `docker-compose up -d` vs running 15 `docker run` commands
- **Networking for free** — services discover each other by name (no IP addresses)
- **Reproducible environments** — anyone can clone your repo and run the same stack
- **Version controlled infra** — your infrastructure definition lives with your code

### Why NOT jump to Kubernetes yet

K8s solves problems you don't have yet:
- Multi-node scheduling (you have 1 machine)
- Auto-scaling under load (you're in development)
- Zero-downtime deployments (not needed locally)
- It adds massive complexity for zero benefit at your stage

### Typical progression

```
Docker Compose (local dev)  ←── YOU ARE HERE
        │
        ▼
Docker Compose on a VPS (small production)
        │
        ▼
Kubernetes (when you need multiple servers, auto-scaling)
```

---

## 7. How Docker Compose Networking Works

```
Your laptop (host machine)
  │
  │ localhost:8000 ──► api-gateway:8000      (your API)
  │ localhost:3000 ──► grafana:3000          (dashboards)
  │ localhost:9090 ──► prometheus:9090       (metrics)
  │
  └── Docker bridge network (smartcourse-network)
        │
        ├── api-gateway ──► user-service:8001      (internal, no host port)
        ├── api-gateway ──► course-service:8002     (internal, no host port)
        ├── prometheus  ──► user-service:8001/metrics
        ├── prometheus  ──► ai-service:8005/metrics
        └── grafana     ──► prometheus:9090
```

- **`ports: "8000:8000"`** = expose to your laptop (host:container)
- **No `ports:`** = only accessible inside Docker network (like your microservices)
- Services find each other by **service name** — Docker runs its own DNS server

---

## 8. URLs Quick Reference

| URL | What | Credentials |
|-----|------|-------------|
| http://localhost:8000 | API Gateway (existing) | — |
| http://localhost:9090 | Prometheus UI | — |
| http://localhost:9090/targets | Check which services are being scraped | — |
| http://localhost:3000 | Grafana dashboards | admin / smartcourse |

---

## 9. Files Summary

After implementation, your new files will be:

```
smart-course/
├── monitoring/
│   ├── prometheus.yml                                  # What to scrape
│   └── grafana/
│       └── provisioning/
│           └── datasources/
│               └── prometheus.yml                      # Auto-connect to Prometheus
├── docker-compose.yml                                  # +2 services, +2 volumes
└── services/*/pyproject.toml                            # +prometheus-fastapi-instrumentator
```

Each FastAPI service needs just **1 new import + 1 line of code** to expose metrics.
