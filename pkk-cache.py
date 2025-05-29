from flask import Flask, request, send_file
from markupsafe import escape
import os
import requests
import logging
import time
import random

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройки слоев
settings = {
    'boundary': {
        'url': 'https://nspd.gov.ru/api/aeggis/v3/36048/wms',
        'params': {
            'REQUEST': 'GetMap',
            'SERVICE': 'WMS',
            'VERSION': '1.3.0',
            'FORMAT': 'image/png',
            'STYLES': '',
            'TRANSPARENT': 'true',
            'LAYERS': '36048',
            'CRS': 'EPSG:3857',
            'WIDTH': 512,
            'HEIGHT': 512
        }
    },
    'building': {
        'url': 'https://nspd.gov.ru/api/aeggis/v3/36049/wms',
        'params': {
            'REQUEST': 'GetMap',
            'SERVICE': 'WMS',
            'VERSION': '1.3.0',
            'FORMAT': 'image/png',
            'STYLES': '',
            'TRANSPARENT': 'true',
            'LAYERS': '36049',
            'CRS': 'EPSG:3857',
            'WIDTH': 512,
            'HEIGHT': 512
        }
    }
}

app = Flask(__name__, static_url_path='')

def generate_referer(bbox):
    """Генерирует Referer на основе bbox"""
    try:
        # Парсим bbox
        minx, miny, maxx, maxy = map(float, bbox.split(','))
        
        # Вычисляем центр
        center_x = (minx + maxx) / 2
        center_y = (miny + maxy) / 2
        
        # Вычисляем зум (очень приблизительно)
        width = maxx - minx
        zoom = 19 - int(width / 1000)  # Эмпирическая формула
        
        return f"https://nspd.gov.ru/map?thematic=PKK&theme_id=1&zoom={zoom}&coordinate_x={center_x}&coordinate_y={center_y}&is_copy_url=true&active_layers=36329%2C36328%2C36049"
    except:
        return "https://nspd.gov.ru/"

@app.route('/')
def index():
    return 'It works!'

@app.route('/path/<path:subpath>')
def static_file(subpath):
    bbox = request.args.get('bbox')
    if not bbox:
        return "Missing bbox parameter", 400
    
    safe_subpath = escape(subpath)
    if safe_subpath not in settings:
        return f"Layer {safe_subpath} not found", 404

    # Создаем безопасное имя файла
    safe_bbox = bbox.replace(',', '_').replace('.', 'd')
    cache_dir = os.path.join('cache', safe_subpath)
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f'{safe_bbox}.png')

    if not os.path.exists(cache_file):
        config = settings[safe_subpath]
        params = config['params'].copy()
        params['BBOX'] = bbox
        
        try:
            logger.info(f"Fetching tile for {safe_subpath} with bbox: {bbox}")
            
            # Добавляем случайное число как в реальном запросе
            params['RANDOM'] = str(random.random())
            
            # Генерируем Referer на основе bbox
            referer = generate_referer(bbox)
            
            # Полные заголовки как в рабочем запросе
            headers = {
                'Accept': 'image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
                'Referer': referer,
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'Priority': 'u=5, i',
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:138.0) Gecko/20100101 Firefox/138.0'
            }
            
            response = requests.get(
                config['url'],
                params=params,
                headers=headers,
                verify=False,
                timeout=30
            )
            
            logger.info(f"Response status: {response.status_code}, URL: {response.url}")
            
            if response.status_code != 200:
                # Проверяем, не является ли ошибка "нет данных"
                if response.status_code == 200 and response.content == b'':
                    logger.warning("Empty response - probably no data for this area")
                    # Создаем прозрачное изображение 512x512
                    from PIL import Image
                    img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
                    img.save(cache_file, 'PNG')
                else:
                    return f"Upstream server error: {response.status_code}", 502
            else:    
                with open(cache_file, 'wb') as f:
                    f.write(response.content)
                
        except Exception as e:
            logger.error(f"Error fetching tile: {str(e)}")
            return f"Error fetching tile: {str(e)}", 500

    return send_file(cache_file, mimetype='image/png')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
