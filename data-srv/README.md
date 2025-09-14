# Soundscape Data Services

This repository contains the data ingestion and tile server services for Soundscape, providing geospatial data processing and API endpoints for accessible navigation applications.

## Overview

These services use **IMPOSM3** ([imposm3](https://github.com/omniscale/imposm3)) to import OpenStreetMap (OSM) data into PostGIS. IMPOSM's mapping facility performs light filtering on OSM data before injecting it into the database.

> **Note:** While questions have been raised about IMPOSM's maintenance level, we have explored alternatives like OSM2PGSQL with `--output=flex` and appropriate LUA styles, which can produce similar results.

## Deployment Options

This data server can be deployed in two ways:

### 1. Standalone Configuration (`docker-compose.yml`)

- Independent data services only
- Direct port access to each service
- Suitable for development or when only data services are needed
- Database exposed on `localhost:5432`
- Tile server on `localhost:8081` (blue) / `localhost:8082` (green)

### 2. Unified Configuration (`../docker-compose.unified.yml`)

- Complete Soundscape solution with authoring tool
- Single entry point through Caddy reverse proxy
- All services accessible via `localhost` with path-based routing
- Internal Docker networking (no direct database access)
- Production-ready with proper load balancing and SSL termination

## Architecture

The system consists of three main components:

1. **PostGIS Database**: Stores processed OSM data
2. **Ingest Service**: Downloads and processes OSM data from various sources
3. **Tile Server**: Serves GeoJSON tiles via HTTP API

## Quick Start

### Standalone Data Services

Default setup (Washington DC):

```bash
cd data-srv
docker-compose up --build
```

Custom region:

```bash
cd data-srv
GEN_REGIONS=andorra docker-compose up --build
```

### Unified Setup (Data Services + Authoring Tool)

From the project root:

```bash
# Copy environment file
cp sample.env .env

# Edit .env file with your configuration
# Especially set AZURE_MAPS_SUBSCRIPTION_KEY

# Start all services
docker-compose -f docker-compose.unified.yml up --build
```

### Available Regions

See `extracts.json` for all available regions including:

- `district-of-columbia` (default)
- `california`
- `toronto`
- `england`
- `andorra`
- And many more...

## Testing the Service

### Standalone Data Server

When using the standalone `docker-compose.yml`, test by fetching a tile directly:

```bash
curl http://localhost:8081/16/18745/25070.json
```

### Unified Setup (with Authoring Tool)

When using `docker-compose.unified.yml` with Caddy proxy, the tile server is accessible at:

```bash
# Through Caddy proxy (recommended)
curl http://localhost/tiles/16/18745/25070.json

# Direct access to service (internal network)
curl http://localhost:8081/16/18745/25070.json  # tilesrv-blue
curl http://localhost:8082/16/18745/25070.json  # tilesrv-green (when active)
```

Use [bboxfinder.com](http://bboxfinder.com/) to find tile coordinates for your region.

## Adding New Regions

### 1. Find OSM Data Source

Visit [Geofabrik Downloads](https://download.geofabrik.de/) and locate the `.osm.pbf` file for your desired region.

### 2. Get Bounding Box Coordinates

Query OpenStreetMap's Nominatim API to get accurate bounding box:

```bash
curl -s "https://nominatim.openstreetmap.org/search?q=YourRegion&format=json&limit=1&extratags=1" | python3 -m json.tool
```

### 3. Add to extracts.json

Add a new entry to `extracts.json`:

```json
{
    "name": "your-region",
    "url": "https://download.geofabrik.de/path/to/your-region-latest.osm.pbf",
    "bbox": [lat_min, lon_min, lat_max, lon_max]
}
```

### 4. Deploy

```bash
GEN_REGIONS=your-region docker-compose up --build
```

## Environment Variables

| Variable      | Default                | Description                          |
| ------------- | ---------------------- | ------------------------------------ |
| `GEN_REGIONS` | `district-of-columbia` | Region to process from extracts.json |
| `LOOP_TIME`   | `14400`                | Update interval in seconds (4 hours) |
| `NAMESPACE`   | `soundscape`           | Application namespace                |

## Blue-Green Deployment

The system supports zero-downtime updates using blue-green deployment:

1. Update green service: `docker compose up --build -d tilesrv-green`
2. Test on port 8082: `http://localhost:8082`
3. Switch Caddy config and reload
4. Remove blue service: `docker compose stop tilesrv-blue`

## Data Sources

### Primary: OpenStreetMap Data

- Downloads `.osm.pbf` files from Geofabrik and other sources
- Processes streets, POIs, buildings, and other geographic features
- Updates can be scheduled for automatic refresh

### Secondary: Custom Non-OSM Data

- CSV files in `non_osm_data/` directory
- Format: `feature_type,feature_value,longitude,latitude,name`
- Assigned unique IDs (>10^17) to avoid OSM conflicts

## API Endpoints

### Standalone Configuration

- **Tiles**: `http://localhost:8081/{z}/{x}/{y}.json` (tilesrv-blue)
- **Tiles Green**: `http://localhost:8082/{z}/{x}/{y}.json` (tilesrv-green, when active)
- **Metrics**: `http://localhost:8083/` (Prometheus format)
- **Database**: `localhost:5432` (PostgreSQL with PostGIS)

### Unified Configuration (with Caddy Proxy)

- **Tiles**: `http://localhost/tiles/{z}/{x}/{y}.json` (through Caddy)
- **Metrics**: `http://localhost/metrics/` (through Caddy)
- **Files**: `http://localhost/files/` (authoring tool files)
- **API**: `http://localhost/api/` (authoring tool API)
- **Database**: Internal network only (postgres-tiles service)

### Caddy Configuration

The unified setup uses Caddy as a reverse proxy with the following routing:

- `/tiles/*` → `tilesrv-blue:8080` (strips `/tiles` prefix)
- `/metrics/*` → `ingest:8083` (strips `/metrics` prefix)
- `/api/*` → `web:8000` (authoring tool backend)
- `/files/*` → `files:80` (file server)
- `/*` → Static frontend files

## Example: Querying Andorra Data

When you configure the system for Andorra (`GEN_REGIONS=andorra`), you can test the tile server with these verified coordinates and URLs:

### Recommended Test Locations

| Location                       | Latitude  | Longitude | Features | Standalone URL                                                   | Unified URL                                                             |
| ------------------------------ | --------- | --------- | -------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------- |
| **Andorra la Vella** (Capital) | `42.5063` | `1.5218`  | 737      | [16/33045/24203.json](http://localhost:8081/16/33045/24203.json) | [tiles/16/33045/24203.json](http://localhost/tiles/16/33045/24203.json) |
| **Escaldes-Engordany**         | `42.5067` | `1.5347`  | 312      | [16/33047/24203.json](http://localhost:8081/16/33047/24203.json) | [tiles/16/33047/24203.json](http://localhost/tiles/16/33047/24203.json) |
| **Geographic Center**          | `42.5407` | `1.5732`  | 7        | [16/33054/24195.json](http://localhost:8081/16/33054/24195.json) | [tiles/16/33054/24195.json](http://localhost/tiles/16/33054/24195.json) |

### Sample Data Verification

```bash
# Check total data loaded
docker-compose exec postgis psql -U postgres -d osm -c "SELECT COUNT(*) FROM osm_roads;"
docker-compose exec postgis psql -U postgres -d osm -c "SELECT COUNT(*) FROM osm_places;"

# Test a high-density tile (Andorra la Vella)
# Standalone setup:
curl "http://localhost:8081/16/33045/24203.json" | jq '.features | length'
# Unified setup:
curl "http://localhost/tiles/16/33045/24203.json" | jq '.features | length'

# View sample places in Andorra
docker-compose exec postgis psql -U postgres -d osm -c "SELECT name, feature_type, feature_value FROM osm_places WHERE name LIKE '%Andorra%' LIMIT 5;"
```

### Database Connection

#### Standalone Configuration

The PostgreSQL database is exposed on `localhost:5432` for external client connections:

```bash
# Connection parameters
Host: localhost
Port: 5432
Database: osm
Username: postgres
Password: secret
```

#### Unified Configuration

In the unified setup, the database is only accessible from within the Docker network as `postgres-tiles` service. For external access, you would need to add port mapping or use `docker exec`:

```bash
# Connect via docker exec
docker exec -it $(docker ps -q -f "name=postgres-tiles") psql -U postgres -d osm
```

Example connection strings:

```bash
# psql command line
psql -h localhost -p 5432 -U postgres -d osm

# Connection URL
postgresql://postgres:secret@localhost:5432/osm
```

### Mobile App Configuration

For mobile applications, use these initial coordinates:

```json
{
  "initialLocation": {
    "latitude": 42.5063,
    "longitude": 1.5218,
    "zoom": 16
  },
  "tileServerUrl": "http://localhost:8081", // Standalone
  "tileServerUrl": "http://localhost/tiles", // Unified
  "boundingBox": {
    "north": 42.6559357,
    "south": 42.4288238,
    "east": 1.7868662,
    "west": 1.4077997
  }
}
```

### Expected Data Coverage

- **Roads**: ~7,187 road segments
- **Places**: ~12,134 points of interest
- **Features**: Hotels, restaurants, government buildings, paths, residential streets
- **Languages**: Primarily Catalan, with some French and Spanish names

## Monitoring

The ingest service provides Prometheus metrics for monitoring:

- Event duration tracking
- Last event timestamps
- Database connection status
