# Grafana Configuration for Soundscape

This directory contains the Grafana configuration for monitoring the Soundscape Authoring Tool and Data Server.

## Structure

```
grafana/
├── provisioning/
│   ├── datasources/
│   │   └── prometheus.yml     # Prometheus datasource configuration
│   └── dashboards/
│       ├── dashboards.yml     # Dashboard provider configuration
│       └── soundscape-monitoring.json # Main monitoring dashboard
```

## Features

### Data Sources

- **Prometheus**: Configured to connect to the ingest service metrics endpoint (`http://ingest:8083`)

### Dashboards

- **Soundscape Monitoring**: Basic dashboard showing:
  - Service health status
  - Service uptime metrics
  - Number of active services

## Access

- **URL**: `http://localhost/grafana/`
- **Default credentials**: admin/admin (configurable via environment variables)

## Configuration

The Grafana service is configured with:

- Persistent storage for dashboards and data
- Auto-provisioned Prometheus datasource
- Pre-configured monitoring dashboard
- Integration with the unified Docker Compose stack

## Environment Variables

Configure these in your `.env` file:

```bash
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
```

## Extending

To add more dashboards:

1. Create new `.json` dashboard files in `grafana/provisioning/dashboards/`
2. They will be automatically loaded on Grafana startup

To add more data sources:

1. Create new YAML files in `grafana/provisioning/datasources/`
2. Follow the Grafana provisioning format

## Metrics Available

The ingest service exposes Prometheus metrics at `/metrics` endpoint, which include:

- Process metrics
- HTTP request metrics
- Custom application metrics
- Go runtime metrics

These are automatically scraped and visualized in the provided dashboard.
