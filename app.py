#SRC MADE BY - STAR GAMER
from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import os

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)
session = requests.Session()

API_KEY = "STAR"                    
BACKGROUND_FILENAME = "outfit.png"    
IMAGE_TIMEOUT = 10                     
CANVAS_SIZE = (800, 800)            
BACKGROUND_MODE = 'cover'             

def fetch_player_info(uid: str):
    url = f"https://infoooooo-v6v5.vercel.app/accinfo?uid={uid}"
    try:
        resp = session.get(url, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None

def fetch_and_process_image(image_url: str, size: tuple = None):
    try:
        resp = session.get(image_url, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGBA")
        if size:
            img = img.resize(size, Image.LANCZOS)
        return img
    except Exception:
        return None

@app.route('/outfit-image', methods=['GET'])
def outfit_image():
    uid = request.args.get('uid')
    key = request.args.get('key')

    if key != API_KEY:
        return jsonify({'error': 'Invalid or missing API key'}), 401
    if not uid:
        return jsonify({'error': 'Missing uid parameter'}), 400

    player_data = fetch_player_info(uid)
    if not player_data:
        return jsonify({'error': 'Failed to fetch player info'}), 500

    profile_info = player_data.get("profileInfo", {})
    outfit_ids = profile_info.get("equippedSkills", []) or []

    required_starts = ["211", "214", "211", "203", "204", "205", "203"]
    fallback_ids = ["211000000", "214000000", "208000000", "203000000",
                    "204000000", "205000000", "212000000"]

    used_ids = set()

    def fetch_outfit_image(idx, code):
        matched = None
        for oid in outfit_ids:
            str_oid = str(oid)
            if str_oid.startswith(code) and str_oid not in used_ids:
                matched = str_oid
                used_ids.add(str_oid)
                break
        if matched is None:
            matched = fallback_ids[idx]
        url = f'https://iconapi.wasmer.app/{matched}'
        return fetch_and_process_image(url, size=(150, 150))

    futures = [executor.submit(fetch_outfit_image, idx, code)
               for idx, code in enumerate(required_starts)]

    bg_path = os.path.join(os.path.dirname(__file__), BACKGROUND_FILENAME)
    try:
        background = Image.open(bg_path).convert("RGBA")
    except FileNotFoundError:
        return jsonify({'error': f'Background image missing: {BACKGROUND_FILENAME}'}), 500

    bg_w, bg_h = background.size

    if CANVAS_SIZE:
        canvas_w, canvas_h = CANVAS_SIZE
        scale = max(canvas_w / bg_w, canvas_h / bg_h) if BACKGROUND_MODE == 'cover' \
                else min(canvas_w / bg_w, canvas_h / bg_h)
        new_w, new_h = int(bg_w * scale), int(bg_h * scale)
        bg_resized = background.resize((new_w, new_h), Image.LANCZOS)
        offset_x = (canvas_w - new_w) // 2
        offset_y = (canvas_h - new_h) // 2
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))
        canvas.paste(bg_resized, (offset_x, offset_y), bg_resized)
    else:
        canvas = background.copy()
        canvas_w, canvas_h = bg_w, bg_h
        offset_x = offset_y = 0
        scale = 1.0

    positions = [
        {'x': 350, 'y': 30, 'width': 150, 'height': 150},   
        {'x': 575, 'y': 130, 'width': 150, 'height': 150},  
        {'x': 665, 'y': 350, 'width': 150, 'height': 150}, 
        {'x': 575, 'y': 550, 'width': 150, 'height': 150},  
        {'x': 350, 'y': 654, 'width': 150, 'height': 150},  
        {'x': 135, 'y': 570, 'width': 150, 'height': 150},  
        {'x': 135, 'y': 130, 'width': 150, 'height': 150}   
    ]

    for idx, future in enumerate(futures):
        img = future.result()
        if not img:
            continue
        pos = positions[idx]
        paste_x = offset_x + int(pos['x'] * scale)
        paste_y = offset_y + int(pos['y'] * scale)
        paste_w = max(1, int(pos['width'] * scale))
        paste_h = max(1, int(pos['height'] * scale))
        resized = img.resize((paste_w, paste_h), Image.LANCZOS)
        canvas.paste(resized, (paste_x, paste_y), resized)

    output = BytesIO()
    canvas.save(output, format='PNG')
    output.seek(0)
    return send_file(output, mimetype='image/png')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
