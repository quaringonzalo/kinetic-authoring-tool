#!/bin/bash

# Script de utilidad para manejar el despliegue unificado
# Uso: ./deploy.sh [start|stop|restart|logs|build|switch-tiles]

set -e

COMPOSE_FILE="docker-compose.unified.yml"

case "$1" in
    start)
        echo "🚀 Iniciando todos los servicios..."
        docker-compose -f $COMPOSE_FILE up -d --build
        echo "✅ Servicios iniciados. Accede a: http://localhost"
        ;;
    
    stop)
        echo "🛑 Deteniendo todos los servicios..."
        docker-compose -f $COMPOSE_FILE down
        echo "✅ Servicios detenidos"
        ;;
    
    restart)
        echo "🔄 Reiniciando servicios..."
        docker-compose -f $COMPOSE_FILE down
        docker-compose -f $COMPOSE_FILE up -d --build
        echo "✅ Servicios reiniciados"
        ;;
    
    logs)
        SERVICE=${2:-""}
        if [ -z "$SERVICE" ]; then
            echo "📋 Mostrando logs de todos los servicios..."
            docker-compose -f $COMPOSE_FILE logs -f
        else
            echo "📋 Mostrando logs de $SERVICE..."
            docker-compose -f $COMPOSE_FILE logs -f $SERVICE
        fi
        ;;
    
    build)
        echo "🔨 Construyendo imágenes..."
        docker-compose -f $COMPOSE_FILE build
        echo "✅ Imágenes construidas"
        ;;
    
    switch-tiles)
        echo "🔄 Cambiando a tilesrv-green..."
        
        # Iniciar tilesrv-green
        docker-compose -f $COMPOSE_FILE --profile tilesrv-green up -d tilesrv-green
        
        # Esperar a que esté listo
        echo "⏳ Esperando a que tilesrv-green esté listo..."
        sleep 30
        
        # Probar tilesrv-green
        if curl -f http://localhost/tiles/healthz >/dev/null 2>&1; then
            echo "✅ tilesrv-green está funcionando"
            
            # Actualizar Caddyfile para usar green
            sed -i 's/tilesrv-blue:8080/tilesrv-green:8080/g' Caddyfile
            
            # Recargar Caddy
            docker-compose -f $COMPOSE_FILE exec caddy caddy reload --config /etc/caddy/Caddyfile
            
            # Detener blue
            docker-compose -f $COMPOSE_FILE stop tilesrv-blue
            
            echo "✅ Cambio completado. Ahora usando tilesrv-green"
        else
            echo "❌ Error: tilesrv-green no responde"
            exit 1
        fi
        ;;
    
    status)
        echo "📊 Estado de los servicios:"
        docker-compose -f $COMPOSE_FILE ps
        ;;
    
    clean)
        echo "🧹 Limpiando contenedores e imágenes no utilizadas..."
        docker-compose -f $COMPOSE_FILE down --volumes --remove-orphans
        docker system prune -f
        echo "✅ Limpieza completada"
        ;;
    
    setup)
        echo "🔧 Configuración inicial..."
        
        # Verificar que existe .env
        if [ ! -f .env ]; then
            if [ -f sample.env ]; then
                cp sample.env .env
                echo "✅ Archivo .env creado desde sample.env"
                echo "⚠️  EDITA EL ARCHIVO .env CON TUS VALORES ANTES DE CONTINUAR"
                exit 1
            else
                echo "❌ Error: No se encontró sample.env para crear .env"
                exit 1
            fi
        fi
        
        # Construir e iniciar servicios
        docker-compose -f $COMPOSE_FILE up -d --build postgres-authoring postgres-tiles
        
        echo "⏳ Esperando a que las bases de datos estén listas..."
        sleep 15
        
        # Ejecutar migraciones
        echo "🔄 Ejecutando migraciones de Django..."
        docker-compose -f $COMPOSE_FILE exec web python manage.py migrate
        
        echo "✅ Configuración inicial completada"
        echo "💡 Para crear un superusuario: ./deploy.sh superuser"
        ;;
    
    superuser)
        echo "👤 Creando superusuario..."
        docker-compose -f $COMPOSE_FILE exec web python manage.py createsuperuser
        ;;
    
    *)
        echo "Uso: $0 {start|stop|restart|logs|build|switch-tiles|status|clean|setup|superuser}"
        echo ""
        echo "Comandos disponibles:"
        echo "  start        - Iniciar todos los servicios"
        echo "  stop         - Detener todos los servicios"
        echo "  restart      - Reiniciar todos los servicios"
        echo "  logs [srv]   - Ver logs (opcional: de un servicio específico)"
        echo "  build        - Construir las imágenes"
        echo "  switch-tiles - Cambiar de tilesrv-blue a tilesrv-green"
        echo "  status       - Ver estado de los servicios"
        echo "  clean        - Limpiar contenedores e imágenes"
        echo "  setup        - Configuración inicial del proyecto"
        echo "  superuser    - Crear superusuario de Django"
        echo ""
        echo "Ejemplos:"
        echo "  $0 logs web              # Ver logs del servicio web"
        echo "  $0 logs                  # Ver logs de todos los servicios"
        exit 1
        ;;
esac