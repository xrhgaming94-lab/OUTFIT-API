from flask import Flask, request, jsonify, send_file
import requests
from PIL import Image, ImageDraw
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

app = Flask(__name__)

executor = ThreadPoolExecutor(max_workers=24)

# Updated info API
INFO_API = "https://star-info.vercel.app/player-info?uid={uid}"
CHAR_API = "https://character-api-vaibhav-production.up.railway.app/api/{avatar_id}"
RAW_CHAR_FALLBACK = "https://raw.githubusercontent.com/hackervaibhav-dot/character-api-vaibhav/main/pngs/{filename}"
ICON_API = "https://iconapi.wasmer.app/{item_id}"
BANNER_API = "https://banner-views-pink.vercel.app/profile?uid={uid}"

TEMPLATE_FILENAME = "outfit.png"
IMAGE_TIMEOUT = 8
CANVAS_SIZE = (1024, 1024)

session = requests.Session()

# connection reuse
adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
session.mount("http://", adapter)
session.mount("https://", adapter)

session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
})

# COORDS

CHAR_BOX = (300, 110, 420, 830)

WEAPON_BOX = (655, 555, 350, 179)
ENTRY_BOX = (748, 740, 155, 155)

HEX_SLOTS = {
    "pant":     (130, 110, 210, 210),
    "top":      (760, 115, 220, 220),
    "gloves":   (780, 290, 220, 220),
    "shoes":    (790, 380, 180, 220),
    "skywing":  (18, 290, 215, 215),
    "styling":  (18, 540, 215, 185),
    "headskin": (140, 695, 185, 215),
}

SLOT_PADDING = {
    "pant": 10,
    "top": 14,
    "shoes": 14,
    "gloves": 18,
    "skywing": 14,
    "styling": 14,
    "headskin": 18,
}

SLOT_ALIGN = {
    "pant": ("center", "center"),
    "top": ("center", "center"),
    "shoes": ("center", "center"),
    "gloves": ("center", "center"),
    "skywing": ("center", "center"),
    "styling": ("center", "center"),
    "headskin": ("center", "center"),
}

SLOT_OFFSET = {
  "top": (-92, -12),
  "shoes": (0, -82),
}

BANNER_BOX = (340, 10, 345, 90)

# helpers

def fetch_json(url):
    try:
        r = session.get(url, timeout=IMAGE_TIMEOUT)
        return r.json()
    except:
        return None

def fetch_image_any(url):
    try:
        r = session.get(url, timeout=IMAGE_TIMEOUT)
        ctype = (r.headers.get("content-type") or "").lower()

        if "application/json" in ctype:
            j = r.json()
            img_url = (
                j.get("url")
                or j.get("image")
                or j.get("png")
                or j.get("link")
                or j.get("banner")
                or j.get("bannerUrl")
                or j.get("banner_url")
            )
            if img_url:
                r = session.get(img_url, timeout=IMAGE_TIMEOUT)

        return Image.open(BytesIO(r.content)).convert("RGBA")
    except:
        return None

def trim_transparent(img):
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    return img.crop(bbox) if bbox else img

def resize_contain(img, w, h):
    iw, ih = img.size
    scale = min(w/iw, h/ih)
    nw = int(iw*scale)
    nh = int(ih*scale)
    return img.resize((nw, nh), Image.LANCZOS)

def paste_in_box(canvas, img, box, pad=12, align=("center","center"), offset=(0,0)):
    x, y, w, h = box

    img = trim_transparent(img)

    img2 = resize_contain(img, w-pad, h-pad)

    px = x + (w - img2.size[0]) // 2
    py = y + (h - img2.size[1]) // 2

    px += offset[0]
    py += offset[1]

    canvas.paste(img2, (px, py), img2)

def safe_text(draw, xy, text):
    draw.text(xy, str(text), fill=(220,255,220,255))

def pick_first_by_prefix(ids, prefix, used, skip_prefixes=None):
    skip_prefixes = skip_prefixes or set()
    for v in ids:
        s = str(v)
        if s in used:
            continue
        if any(s.startswith(sp) for sp in skip_prefixes):
            continue
        if s.startswith(prefix):
            used.add(s)
            return s
    return None

def map_clothes_to_slots(clothes):
    clothes = clothes or []
    used = set()
    skip = {"214"}

    pant = pick_first_by_prefix(clothes, "204", used, skip)
    top = pick_first_by_prefix(clothes, "203", used, skip)
    shoes = pick_first_by_prefix(clothes, "205", used, skip)
    styling = pick_first_by_prefix(clothes, "211", used, skip)
    skywing = pick_first_by_prefix(clothes, "212", used, skip)
    gloves = pick_first_by_prefix(clothes, "208", used, skip)

    return {
        "pant": pant,
        "top": top,
        "shoes": shoes,
        "styling": styling,
        "skywing": skywing,
        "gloves": gloves,
    }

def classify_weapon_entry(item_imgs):
    valid = []
    for item_id, img in item_imgs:
        if not img:
            continue
        w, h = img.size
        if h <= 0:
            continue
        ar = w/h
        valid.append((item_id, img, ar))

    if not valid:
        return None, None

    weapon = max(valid, key=lambda x: x[2])
    remaining = [v for v in valid if v[0] != weapon[0]]
    entry = None
    if remaining:
        entry = min(remaining, key=lambda x: abs(x[2] - 1.0))

    return (weapon[0], weapon[1]), (entry[0], entry[1]) if entry else None

@app.route("/outfit-card", methods=["GET"])
def outfit_card():
    uid = request.args.get("uid")
    if not uid:
        return jsonify({"error": "Missing uid"}), 400

    data = fetch_json(INFO_API.format(uid=uid))
    if not data:
        return jsonify({"error": "player fetch fail"}), 500

    basic = data.get("basicInfo") or {}
    profile = data.get("profileInfo") or {}
    clan = data.get("clanBasicInfo") or {}

    nickname = basic.get("nickname") or ""
    level = basic.get("level") or ""
    liked = basic.get("liked") or ""
    region = basic.get("region") or ""
    avatar_id = str(profile.get("avatarId") or "")

    base = Image.open(TEMPLATE_FILENAME).convert("RGBA")
    if base.size != CANVAS_SIZE:
        base = base.resize(CANVAS_SIZE)
    draw = ImageDraw.Draw(base)

    # PARALLEL TASKS
    futures = {}
    futures["banner"] = executor.submit(fetch_image_any, BANNER_API.format(uid=uid))

    if avatar_id:
        futures["char"] = executor.submit(fetch_image_any, CHAR_API.format(avatar_id=avatar_id))

    clothes = profile.get("clothes", []) or []
    mapped = map_clothes_to_slots(clothes)

    for slot, item in mapped.items():
        if item:
            futures[slot] = executor.submit(fetch_image_any, ICON_API.format(item_id=item))

    skins = basic.get("weaponSkinShows", []) or []
    for i, sid in enumerate(skins[:6]):
        futures[f"skin{i}"] = executor.submit(fetch_image_any, ICON_API.format(item_id=str(sid)))

    results = {k: f.result() for k, f in futures.items()}

    banner = results.get("banner")
    if banner:
        paste_in_box(base, banner, BANNER_BOX)

    char = results.get("char")
    if char:
        paste_in_box(base, char, CHAR_BOX)

    for slot in mapped:
        img = results.get(slot)
        if img:
            paste_in_box(base, img, HEX_SLOTS[slot], offset=SLOT_OFFSET.get(slot, (0, 0)))

    skin_imgs = []
    for i, sid in enumerate(skins[:6]):
        skin_imgs.append((str(sid), results.get(f"skin{i}")))

    weapon_pick, entry_pick = classify_weapon_entry(skin_imgs)
    if weapon_pick:
        paste_in_box(base, weapon_pick[1], WEAPON_BOX)
    if entry_pick:
        paste_in_box(base, entry_pick[1], ENTRY_BOX)

    # Draw text info
    safe_text(draw, (35, 35), nickname)
    safe_text(draw, (35, 80), f"Level {level} | ♥ {liked}")
    safe_text(draw, (35, 120), f"UID {uid} | {region}")

    member_num = clan.get("memberNum")
    capacity = clan.get("capacity")
    if member_num and capacity:
        safe_text(draw, (35, 160), f"Clan: {member_num}/{capacity}")

    out = BytesIO()
    base.save(out, "PNG")
    out.seek(0)
    return send_file(out, mimetype="image/png")

@app.route("/favicon.ico")
def favicon():
    return ("", 204)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
