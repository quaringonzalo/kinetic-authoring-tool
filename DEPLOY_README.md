# Despliegue Unificado - Soundscape Authoring Tool

Esta configuración unifica el authoring tool y el data server en un solo despliegue usando Caddy como proxy reverso.

## 🏗️ Arquitectura

```
Internet → Caddy (Puerto 80/443) → Servicios Internos
                  ↓
    ┌─────────────┼─────────────┐
    │             │             │
    │   /api/*    │  /files/*   │  /tiles/*
    │     ↓       │     ↓       │     ↓
    │  Django     │   Nginx     │  TileServer
    │ (port 8000) │ (port 80)   │ (port 8080)
    │     ↓       │             │     ↓
    │ PostgreSQL  │             │ PostGIS
    │ (port 5432) │             │ (port 5432)
    └─────────────┴─────────────┴─────────────┘
```

## 📍 Rutas del sistema

| Ruta         | Servicio       | Descripción                           |
| ------------ | -------------- | ------------------------------------- |
| `/`          | Frontend       | Aplicación React (archivos estáticos) |
| `/api/*`     | Django Backend | API REST del authoring tool           |
| `/admin/*`   | Django Admin   | Panel de administración               |
| `/files/*`   | Nginx Files    | Archivos GPX y recursos               |
| `/tiles/*`   | TileServer     | Tiles GeoJSON del data server         |
| `/metrics/*` | Ingest         | Métricas Prometheus (opcional)        |

## 🚀 Inicio rápido

### 1. Configuración inicial

```bash
# Clonar y configurar
git clone <repo>
cd authoring-tool

# Configurar variables de entorno
cp sample.env .env
# Editar .env con tus valores

# Configuración inicial (crea DBs y migraciones)
./deploy.sh setup
```

### 2. Crear superusuario

```bash
./deploy.sh superuser
```

### 3. Iniciar todos los servicios

```bash
./deploy.sh start
```

Accede a: `http://localhost`

## 🛠️ Comandos disponibles

| Comando                       | Descripción                                     |
| ----------------------------- | ----------------------------------------------- |
| `./deploy.sh start`           | Iniciar todos los servicios                     |
| `./deploy.sh stop`            | Detener todos los servicios                     |
| `./deploy.sh restart`         | Reiniciar servicios                             |
| `./deploy.sh logs [servicio]` | Ver logs                                        |
| `./deploy.sh status`          | Estado de servicios                             |
| `./deploy.sh switch-tiles`    | Cambiar a tilesrv-green (blue-green deployment) |

## 🔧 Configuración para VPS

### Variables de entorno importantes (.env)

```bash
# Django
SECRET_KEY=tu-secret-key-muy-segura
DEBUG=False
ALLOWED_HOSTS=tu-dominio.com,localhost

# Base de datos authoring tool
PSQL_DB_USER=postgres
PSQL_DB_PASS=password-seguro
PSQL_DB_NAME=authoring_tool

# Azure Maps
AZURE_MAPS_SUBSCRIPTION_KEY=tu-key

# Archivos
FILES_DIR=/ruta/absoluta/a/archivos

# Data server (opcional, usar defaults)
GEN_REGIONS=district-of-columbia
LOOP_TIME=14400
```

### Para producción con dominio

1. Editar `Caddyfile` y descomenta la sección de producción
2. Cambiar `tu-dominio.com` por tu dominio real
3. Caddy se encargará automáticamente del SSL

## 🗄️ Bases de datos

El sistema usa **dos bases de datos PostgreSQL separadas**:

1. **postgres-authoring** (puerto interno 5432)

   - Para el authoring tool (Django)
   - Datos: actividades, usuarios, configuración

2. **postgres-tiles** (puerto interno 5432, red aislada)
   - Para el data server (PostGIS)
   - Datos: tiles OSM, geometrías

## 🔄 Blue-Green Deployment para Tiles

El sistema soporta actualizaciones sin downtime para el tile server:

```bash
# Cambiar a la versión green
./deploy.sh switch-tiles

# El script automáticamente:
# 1. Inicia tilesrv-green
# 2. Verifica que funcione
# 3. Actualiza Caddy para usar green
# 4. Detiene tilesrv-blue
```

## 📊 Monitoreo

- **Logs**: `./deploy.sh logs`
- **Estado**: `./deploy.sh status`
- **Métricas**: `http://localhost/metrics/` (Prometheus de ingest)
- **Health checks**: Configurados para todos los servicios

## 🔐 Seguridad

### Para desarrollo

- Puerto 80 sin SSL
- CORS permisivo
- Debug habilitado

### Para producción

- HTTPS automático con Caddy
- Headers de seguridad configurados
- CORS restrictivo a dominios específicos
- Debug deshabilitado

## 🐛 Solución de problemas

### Puertos ocupados

Si tienes servicios corriendo en los puertos por defecto:

```bash
# Ver qué está usando los puertos
sudo lsof -i :80
sudo lsof -i :5432

# Detener servicios conflictivos o cambiar puertos
```

### Problemas con volúmenes

```bash
# Limpiar todo y empezar de cero
./deploy.sh clean
./deploy.sh setup
```

### Ver logs específicos

```bash
./deploy.sh logs web          # Django
./deploy.sh logs caddy        # Proxy
./deploy.sh logs tilesrv-blue # Tiles
./deploy.sh logs ingest       # Ingesta de datos
```

## 📁 Estructura de archivos

```
authoring-tool/
├── docker-compose.unified.yml  # Configuración completa
├── Caddyfile                   # Configuración del proxy
├── nginx-files.conf            # Config interna de archivos
├── deploy.sh                   # Script de utilidades
├── .env                        # Variables de entorno
├── backend/                    # Django authoring tool
├── frontend/                   # React frontend
├── data-srv/                   # Data server
└── USER_GUIDE/                 # Documentación
```

## 🌐 URLs de ejemplo

- **Frontend**: `http://localhost/`
- **API**: `http://localhost/api/activities/`
- **Admin**: `http://localhost/admin/`
- **Archivos**: `http://localhost/files/activity.gpx`
- **Tiles**: `http://localhost/tiles/16/18745/25070.json`
- **Métricas**: `http://localhost/metrics/`
