# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

# commenting out all azure stuff

import os
import requests
from http import HTTPStatus
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse

# AZURE_MAPS_SUBSCRIPTION_KEY = os.environ.get('AZURE_MAPS_SUBSCRIPTION_KEY')
# if AZURE_MAPS_SUBSCRIPTION_KEY == None:
#     raise Exception('Invalid Azure Maps subscription key')


@require_http_methods(["GET"])
def map(request):
    """
    Returns a mock map tile (Azure Maps functionality commented out).

    Soundscape Authoring is a publicly exposed application, so we use server-to-server
    access to Azure Maps REST APIs so the subscription key can be securely stored.

    More info: https://docs.microsoft.com/en-us/rest/api/maps/render-v2/get-map-tile
    """
    x = request.GET.get('x')
    y = request.GET.get('y')
    zoom = request.GET.get('zoom')

    if x == None or y == None or zoom == None:
        return JsonResponse({'error': 'Missing required parameters'}, status=HTTPStatus.BAD_REQUEST)

    tileset_id = request.GET.get('tileset_id', "microsoft.base.road")
    tile_size = request.GET.get('tile_size', "256")
    language = request.GET.get('language', "en-US")
    view = request.GET.get('view', "Auto")

    # Mock response - return a simple JSON message
    return JsonResponse({
        'message': 'Mock map tile endpoint',
        'coordinates': {
            'x': x,
            'y': y,
            'zoom': zoom
        },
        'parameters': {
            'tileset_id': tileset_id,
            'tile_size': tile_size,
            'language': language,
            'view': view
        },
        'status': 'success'
    })
