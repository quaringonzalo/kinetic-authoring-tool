import os
import requests
from flask import Flask, request, Response
from http import HTTPStatus
from dotenv import load_dotenv

# Cargar variables de entorno desde archivo .env
load_dotenv()

app = Flask(__name__)

# Obtener la clave de suscripción de Azure Maps
AZURE_MAPS_SUBSCRIPTION_KEY = os.environ.get('AZURE_MAPS_SUBSCRIPTION_KEY')

if AZURE_MAPS_SUBSCRIPTION_KEY is None:
    raise Exception('Invalid Azure Maps subscription key. Please set AZURE_MAPS_SUBSCRIPTION_KEY environment variable.')

@app.route('/map', methods=['GET'])
def map_tiles():
    """
    Returns a map tile from Azure Maps.

    Parámetros requeridos:
    - x: Coordenada X del tile
    - y: Coordenada Y del tile
    - zoom: Nivel de zoom

    Parámetros opcionales:
    - tileset_id: ID del tileset (default: microsoft.base.road)
    - tile_size: Tamaño del tile (default: 256)
    - language: Idioma (default: en-US)
    - view: Vista del mapa (default: Auto)

    Ejemplo de uso:
    http://localhost:5000/map?x=134&y=85&zoom=8
    """

    # Obtener parámetros requeridos
    x = request.args.get('x')
    y = request.args.get('y')
    zoom = request.args.get('zoom')

    if x is None or y is None or zoom is None:
        return Response('Missing required parameters: x, y, zoom',
                       status=HTTPStatus.BAD_REQUEST)

    # Obtener parámetros opcionales con valores por defecto
    tileset_id = request.args.get('tileset_id', 'microsoft.base.road')
    tile_size = request.args.get('tile_size', '256')
    language = request.args.get('language', 'en-US')
    view = request.args.get('view', 'Auto')

    # Preparar parámetros para la API de Azure Maps
    params = {
        'api-version': '2.1',
        'subscription-key': AZURE_MAPS_SUBSCRIPTION_KEY,
        'tilesetId': tileset_id,
        'tileSize': tile_size,
        'language': language,
        'view': view,
        'zoom': zoom,
        'x': x,
        'y': y
    }

    try:
        # Hacer petición a Azure Maps
        tile_response = requests.get("https://atlas.microsoft.com/map/tile",
                                   params=params,
                                   timeout=10)

        # Crear respuesta Flask
        response = Response()
        response.status_code = tile_response.status_code
        response.data = tile_response.content

        # Copiar headers importantes
        headers_to_copy = [
            "Cache-Control",
            "Content-Length",
            "Content-Type",
            "Date",
            "ETag",
            "Expires"
        ]

        for header_key in headers_to_copy:
            header_value = tile_response.headers.get(header_key)
            if header_value is not None:
                response.headers[header_key] = header_value

        return response

    except requests.exceptions.RequestException as e:
        return Response(f'Error connecting to Azure Maps: {str(e)}',
                       status=HTTPStatus.INTERNAL_SERVER_ERROR)

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint para verificar que la API está funcionando"""
    return {
        'status': 'healthy',
        'azure_maps_key_configured': AZURE_MAPS_SUBSCRIPTION_KEY is not None
    }

@app.route('/', methods=['GET'])
def home():
    """Página de inicio con información de uso"""
    return """
    <h1>Azure Maps Local API</h1>
    <p>API local para servir tiles de Azure Maps</p>

    <h3>Endpoints disponibles:</h3>
    <ul>
        <li><strong>/map</strong> - Obtener tiles del mapa</li>
        <li><strong>/health</strong> - Verificar estado de la API</li>
    </ul>

    <h3>Ejemplo de uso:</h3>
    <pre>/map?x=134&y=85&zoom=8</pre>

    <h3>Parámetros:</h3>
    <ul>
        <li><strong>x, y, zoom</strong> - Requeridos: coordenadas y nivel de zoom</li>
        <li><strong>tileset_id</strong> - Opcional: tipo de mapa (default: microsoft.base.road)</li>
        <li><strong>tile_size</strong> - Opcional: tamaño del tile (default: 256)</li>
        <li><strong>language</strong> - Opcional: idioma (default: en-US)</li>
        <li><strong>view</strong> - Opcional: vista del mapa (default: Auto)</li>
    </ul>
    """

if __name__ == '__main__':
    print("🗺️  Iniciando Azure Maps Local API...")
    print(f"🔑 Azure Maps Key configurada: {'✅ Sí' if AZURE_MAPS_SUBSCRIPTION_KEY else '❌ No'}")
    print("🚀 API disponible en: http://localhost:5000")
    print("📊 Health check: http://localhost:5000/health")
    print("🗺️  Ejemplo: http://localhost:5000/map?x=134&y=85&zoom=8")

    app.run(debug=True, host='0.0.0.0', port=5000)
