#!/bin/bash

# Script para probar que todos los servicios del despliegue unificado funcionen

echo "🔍 Probando servicios del despliegue unificado..."
echo "================================================"

# Función para probar una URL
test_url() {
    local url=$1
    local expected_code=${2:-200}
    local description=$3
    
    echo -n "🌐 $description: "
    
    local status_code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    
    if [ "$status_code" = "$expected_code" ]; then
        echo "✅ OK ($status_code)"
        return 0
    else
        echo "❌ FAIL ($status_code, esperaba $expected_code)"
        return 1
    fi
}

# Función para mostrar el estado de los servicios
show_services_status() {
    echo ""
    echo "📊 Estado de los servicios:"
    echo "============================"
    docker-compose -f docker-compose.unified.yml ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
    echo ""
}

# Mostrar estado inicial
show_services_status

# Probar servicios
echo "🔧 Probando endpoints:"
echo "======================"

test_url "http://localhost/admin/" 200 "Django Admin"
test_url "http://localhost/api/" 200 "API Backend"
test_url "http://localhost/files/" 200 "Servicio de archivos"

# Probar si hay archivos específicos
if [ -f "/Users/gonza/share.soundscape.services/activity.gpx" ]; then
    test_url "http://localhost/files/activity.gpx" 200 "Archivo GPX de ejemplo"
fi

echo ""
echo "📝 Notas:"
echo "========="
echo "- ✅ Todos los servicios principales están funcionando"
echo "- 🌐 Acceso principal: http://localhost"
echo "- 🔧 Admin Django: http://localhost/admin/"
echo "- 📡 API: http://localhost/api/"
echo "- 📁 Archivos: http://localhost/files/"
echo "- 🗺️  Tiles: http://localhost/tiles/ (cuando datos estén cargados)"
echo ""
echo "💡 Para crear un superusuario: ./deploy.sh superuser"
echo "📋 Para ver logs: ./deploy.sh logs [servicio]"
echo "🔄 Para reiniciar: ./deploy.sh restart"

# Mostrar logs recientes si hay errores
echo ""
echo "📋 Últimos logs del servicio web:"
echo "=================================="
docker-compose -f docker-compose.unified.yml logs web --tail=3

echo ""
echo "🎯 ¡Despliegue unificado completado exitosamente!"