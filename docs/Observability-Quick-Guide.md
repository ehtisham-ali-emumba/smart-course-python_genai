# SmartCourse Observability Quick Guide

## What You Have

SmartCourse now has an observability stack made of:

- Prometheus: collects metrics from services and infrastructure
- Grafana: visualizes those metrics in dashboards
- Alertmanager: receives and groups alerts from Prometheus
- Exporters: small services that convert infrastructure state into Prometheus metrics

Main URLs:

- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- Alertmanager: http://localhost:9093
- cAdvisor: http://localhost:8085

## How It Works Under the Hood

### 1. Metrics are exposed

Each service exposes a `/metrics` endpoint.

- user-service, course-service, notification-service, core-service, ai-service
- auth-sidecar

Infrastructure exporters also expose metrics:

- node-exporter: host or Docker VM CPU, memory, disk, network
- cadvisor: per-container CPU, memory, filesystem, network
- postgres-exporter: PostgreSQL metrics
- redis-exporter: Redis metrics
- mongodb-exporter: MongoDB metrics
- kafka-exporter: Kafka lag and broker metrics
- rabbitmq built-in Prometheus plugin: queue metrics
- nginx-exporter: gateway connection and request metrics

### 2. Prometheus scrapes metrics

Prometheus polls each target every 15 seconds.

It stores time-series data such as:

- request counts
- latency histograms
- CPU and memory usage
- queue depth
- database connections

### 3. Prometheus evaluates rules

Prometheus uses two rule types:

- recording rules: precompute common queries for faster dashboards
- alert rules: detect bad states like service down, high CPU, queue backlog

### 4. Alertmanager handles alerts

When an alert condition is true long enough, Prometheus sends it to Alertmanager.

Alertmanager then:

- groups alerts
- suppresses noisy duplicates
- prepares routing for future integrations like Slack or PagerDuty

### 5. Grafana reads from Prometheus

Grafana does not collect metrics directly.

It queries Prometheus and renders dashboards so you can see trends, spikes, and failures.

## Dashboard Guide

### 1. SmartCourse Overview

This is the main health dashboard.

What it shows:

- service UP or DOWN state
- total request rate
- 5xx error rate
- overall p95 latency
- host CPU, memory, disk usage
- active alerts

Use it for:

- checking if the platform is generally healthy
- spotting whether a problem is application-side or infrastructure-side
- seeing whether Prometheus already thinks something is wrong

How to read it:

- green service stat means Prometheus can scrape that service
- rising 5xx errors means server-side failures are happening
- high p95 latency means users are feeling slowness even if average latency looks okay
- active alerts panel tells you what Prometheus is already flagging

### 2. SmartCourse Services

This is the application drill-down dashboard.

What it shows:

- request rate by endpoint
- p50, p95, p99 latency by endpoint
- 4xx and 5xx breakdowns
- in-progress requests
- top slow endpoints

Use it for:

- debugging one service at a time
- finding slow routes
- seeing whether traffic spikes match latency spikes
- distinguishing client errors from server errors

How to read it:

- high request rate on one endpoint can explain higher latency
- high p99 with normal p50 usually means tail latency or intermittent slowness
- growing in-progress requests can indicate saturation, blocking I/O, or dependency slowdown
- top slow endpoints table tells you where to start debugging in code

### 3. SmartCourse Containers

This is the Docker resource dashboard.

What it shows:

- CPU usage per container
- memory usage per container
- memory vs configured limit
- network receive and transmit
- filesystem reads and writes

Use it for:

- spotting memory leaks
- finding CPU-heavy services
- seeing if one container is behaving abnormally compared to others

How to read it:

- one container with steadily climbing memory often means a leak or oversized caching
- CPU spikes during specific operations can confirm workload hotspots
- memory vs limit is only fully meaningful if service memory limits are configured

### 4. SmartCourse Databases

This is the data-layer health dashboard.

What it shows:

- PostgreSQL connections, transaction rate, database size
- Redis memory use, hit ratio, clients, evictions, command rate
- MongoDB connections, operations per second, resident memory

Use it for:

- detecting database bottlenecks
- identifying cache pressure in Redis
- checking whether MongoDB activity matches application traffic

How to read it:

- high PostgreSQL connection count can signal pool exhaustion risk
- low Redis hit ratio means cache effectiveness is poor
- Redis evictions mean memory pressure is real
- high MongoDB connections with slow app behavior can indicate backend pressure

### 5. SmartCourse Messaging

This is the async pipeline dashboard.

What it shows:

- Kafka consumer lag by topic and consumer group
- Kafka message throughput
- Kafka broker count
- RabbitMQ queue depth
- RabbitMQ consumers per queue
- RabbitMQ publish and delivery rates

Use it for:

- checking whether event-driven processing is keeping up
- detecting stuck workers or falling-behind consumers
- understanding whether background systems are healthy when APIs still look fine

How to read it:

- growing Kafka lag means consumers are not keeping up with produced events
- rising RabbitMQ queue depth usually means workers are slow, blocked, or under-scaled
- low consumer count on an expected queue may mean a worker crashed or never started

## What Happens During a Real Incident

Example: users complain that enrolling in a course is slow.

Check in this order:

1. Overview dashboard

- Is request latency rising?
- Are there active alerts?

2. Services dashboard

- Is the course-service `/course/enrollments` endpoint slow?
- Are in-progress requests increasing?

3. Databases dashboard

- Is PostgreSQL connection count too high?
- Is Redis unhealthy?

4. Messaging dashboard

- Is Kafka lag growing after enrollments?
- Is RabbitMQ queue depth increasing?

5. Containers dashboard

- Is one service CPU or memory saturated?

This is the normal lead-level flow: start broad, narrow to service, then dependency, then infrastructure.

## What “UP” Actually Means

In Prometheus, `UP` means Prometheus successfully scraped a metrics endpoint.

It does not always mean the service is fully healthy for users.

Examples:

- a service can be UP but returning 500s
- a service can be UP but very slow
- a queue can be UP but badly backlogged

That is why you need dashboards plus alerts, not just health checks.

## What To Watch Regularly

Daily checks:

- any firing alerts
- error rate
- p95 latency
- Kafka lag
- RabbitMQ queue depth
- Redis evictions
- PostgreSQL connections
- container memory growth trends

## Local Development Notes

On macOS with Docker Desktop:

- node-exporter reports Docker VM metrics, not macOS host-native metrics
- cadvisor still reports useful container-level metrics
- some container memory ratio views are less useful unless explicit memory limits are added in compose

## Best-Practice Mental Model

Use observability in this order:

1. Symptoms: Overview dashboard
2. Service behavior: Services dashboard
3. Dependencies: Databases and Messaging dashboards
4. Resource pressure: Containers dashboard
5. Root cause confirmation: Prometheus queries and service logs
