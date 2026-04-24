import base64
import hashlib
import ipaddress
import json
import math
import mimetypes
import os
import platform
import re
import socket
import struct
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from ctypes import Structure, byref, c_ulong, c_ulonglong, sizeof, windll
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, LEFT, RIGHT, BOTTOM, X, Y, Canvas, StringVar, Text, Tk, filedialog
import tkinter as tk


APP_NAME = "Schizo Osint"
APP_FOOTER = "Desktop GEOINT and visual notes"
TG_LINK = "https://t.me/SchizoOsint"
DISCORD_LINK = "https://discord.gg/Ddcf2dnMF"
STATS_FILE = Path(__file__).with_name("app_stats.json")
MEDIA_PREVIEW_DIR = Path(__file__).with_name(".media_previews")

BG = "#07111d"
PANEL = "#0d1b2d"
CARD = "#10233a"
CARD_ALT = "#16314b"
CARD_SOFT = "#1b3c58"
ACCENT = "#57d4ff"
ACCENT_2 = "#84f3b5"
ACCENT_3 = "#ffcf70"
TEXT = "#f4f7fb"
MUTED = "#95a9c6"
WARN = "#ffb86b"
EARTH = "#08131f"
NODE_FILL = "#173048"
NODE_ACTIVE = "#24537b"
NODE_LINE = "#4d90b8"

MAP_TILE_SIZE = 256
MAP_MIN_ZOOM = 2
MAP_MAX_ZOOM = 17
MAP_USER_AGENT = "SchizoOsint/2.0"
IP_SERVICES = (
    "https://ipwho.is/{query}",
    "https://ipapi.co/{query}/json/",
)


class MEMORYSTATUSEX(Structure):
    _fields_ = [
        ("dwLength", c_ulong),
        ("dwMemoryLoad", c_ulong),
        ("ullTotalPhys", c_ulonglong),
        ("ullAvailPhys", c_ulonglong),
        ("ullTotalPageFile", c_ulonglong),
        ("ullAvailPageFile", c_ulonglong),
        ("ullTotalVirtual", c_ulonglong),
        ("ullAvailVirtual", c_ulonglong),
        ("ullAvailExtendedVirtual", c_ulonglong),
    ]


@dataclass
class NodeItem:
    node_id: int
    node_type: str
    title: str
    body: str
    x: float
    y: float
    media_path: str = ""


def round_rect(canvas, x1, y1, x2, y2, radius=18, fill=CARD, outline=""):
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, fill=fill, outline=outline)


def fetch_text(url, timeout=5):
    request = urllib.request.Request(url, headers={"User-Agent": MAP_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def fetch_json(url, timeout=5):
    return json.loads(fetch_text(url, timeout=timeout))


def fetch_bytes(url, timeout=5):
    request = urllib.request.Request(url, headers={"User-Agent": MAP_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def get_local_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "Недоступно"


def get_public_ip():
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            return fetch_text(url, timeout=2.5).strip()
        except Exception:
            continue
    return "Недоступно"


def probe_latency():
    for host, port in (("1.1.1.1", 53), ("8.8.8.8", 53)):
        start = time.perf_counter()
        try:
            sock = socket.create_connection((host, port), timeout=1.6)
            sock.close()
            return f"{round((time.perf_counter() - start) * 1000)} ms"
        except OSError:
            continue
    return "Недоступно"


def format_gb(size_bytes):
    return f"{size_bytes / (1024 ** 3):.2f} GB"


def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    return f"{size_bytes / (1024 ** 3):.2f} GB"


def get_total_memory():
    try:
        stat = MEMORYSTATUSEX()
        stat.dwLength = sizeof(MEMORYSTATUSEX)
        windll.kernel32.GlobalMemoryStatusEx(byref(stat))
        return format_gb(stat.ullTotalPhys)
    except Exception:
        return "Недоступно"


def load_stats():
    default = {"launches": 0, "last_opened": None}
    if not STATS_FILE.exists():
        return default
    try:
        return {**default, **json.loads(STATS_FILE.read_text(encoding="utf-8"))}
    except Exception:
        return default


def save_stats(stats):
    STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_coordinates(text):
    cleaned = text.replace(";", " ").replace("|", " ").replace("\n", " ")
    cleaned = cleaned.replace("lat", " ").replace("lon", " ").replace("lng", " ")
    for chunk in cleaned.split():
        parts = chunk.split(",")
        if len(parts) == 2:
            try:
                lat = float(parts[0])
                lon = float(parts[1])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return lat, lon
            except ValueError:
                continue
    tokens = cleaned.replace(",", " ").split()
    for index in range(len(tokens) - 1):
        try:
            lat = float(tokens[index])
            lon = float(tokens[index + 1])
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            continue
    return None


def clamp_lat(lat):
    return max(-85.0511, min(85.0511, lat))


def clamp_lon(lon):
    while lon < -180:
        lon += 360
    while lon > 180:
        lon -= 360
    return lon


def world_to_latlon(world_x, world_y, zoom):
    scale = MAP_TILE_SIZE * (2 ** zoom)
    lon = world_x / scale * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * world_y / scale
    lat = math.degrees(math.atan(math.sinh(n)))
    return clamp_lat(lat), clamp_lon(lon)


def latlon_to_world(lat, lon, zoom):
    lat = clamp_lat(lat)
    lon = clamp_lon(lon)
    scale = MAP_TILE_SIZE * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * scale
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * scale
    return x, y


def is_ip_query(query):
    try:
        ipaddress.ip_address(query)
        return True
    except ValueError:
        return False


def resolve_location(query):
    query = query.strip()
    coords = parse_coordinates(query)
    if coords:
        lat, lon = coords
        return {"kind": "coordinates", "lat": lat, "lon": lon, "label": f"{lat:.5f}, {lon:.5f}", "details": "Coordinates parsed from input"}

    if is_ip_query(query):
        for template in IP_SERVICES:
            try:
                payload = fetch_json(template.format(query=urllib.parse.quote(query)), timeout=5)
            except Exception:
                continue
            lat = payload.get("latitude", payload.get("lat"))
            lon = payload.get("longitude", payload.get("lon"))
            if lat is None or lon is None:
                continue
            city = payload.get("city") or "Unknown city"
            country = payload.get("country") or payload.get("country_name") or "Unknown country"
            return {"kind": "ip", "lat": float(lat), "lon": float(lon), "label": f"{query} -> {city}, {country}", "details": "Approximate IP geolocation"}
        raise RuntimeError("IP service did not return coordinates")

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": 1})
    results = fetch_json(url, timeout=6)
    if not results:
        raise RuntimeError("No location found for the query")
    item = results[0]
    return {"kind": "address", "lat": float(item["lat"]), "lon": float(item["lon"]), "label": item.get("display_name", query), "details": "OpenStreetMap geocoding result"}


def file_sha256(file_path):
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_media_kind(file_path):
    suffix = Path(file_path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}:
        return "image"
    if suffix in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        return "video"
    if suffix in {".mp3", ".wav", ".ogg", ".flac", ".m4a"}:
        return "audio"
    return "file"


def read_png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def read_gif_size(data):
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    return struct.unpack("<HH", data[6:10])


def read_bmp_size(data):
    if data[:2] != b"BM":
        return None
    width, height = struct.unpack("<ii", data[18:26])
    return abs(width), abs(height)


def read_webp_size(data):
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8 " and len(data) >= 30:
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    return None


def read_jpeg_size(data):
    if not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    while index < len(data) - 1:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        while marker == 0xFF and index < len(data):
            marker = data[index]
            index += 1
        if marker in (0xD8, 0xD9):
            continue
        if index + 2 > len(data):
            break
        size = struct.unpack(">H", data[index:index + 2])[0]
        if size < 2 or index + size > len(data):
            break
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height = struct.unpack(">H", data[index + 3:index + 5])[0]
            width = struct.unpack(">H", data[index + 5:index + 7])[0]
            return width, height
        index += size
    return None


def tiff_unpack(endian, fmt, blob):
    return struct.unpack(("<" if endian == "I" else ">") + fmt, blob)


def read_tiff_value(data, base, endian, field_type, count, value_offset_pos):
    type_sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8}
    size = type_sizes.get(field_type, 1) * count
    value_or_offset = data[value_offset_pos:value_offset_pos + 4]
    if size <= 4:
        raw = value_or_offset[:size]
    else:
        offset = tiff_unpack(endian, "I", value_or_offset)[0]
        raw = data[base + offset: base + offset + size]
    if field_type == 2:
        return raw.rstrip(b"\x00").decode("utf-8", errors="ignore")
    if field_type == 3:
        return tiff_unpack(endian, "H" * count, raw)
    if field_type == 4:
        return tiff_unpack(endian, "I" * count, raw)
    if field_type == 5:
        values = []
        for index in range(count):
            numerator = tiff_unpack(endian, "I", raw[index * 8:index * 8 + 4])[0]
            denominator = tiff_unpack(endian, "I", raw[index * 8 + 4:index * 8 + 8])[0]
            values.append((numerator, denominator))
        return tuple(values)
    return raw


def parse_ifd(data, base, offset, endian):
    if base + offset + 2 > len(data):
        return {}
    count = tiff_unpack(endian, "H", data[base + offset:base + offset + 2])[0]
    tags = {}
    entry_start = base + offset + 2
    for index in range(count):
        pos = entry_start + index * 12
        if pos + 12 > len(data):
            break
        tag, field_type, value_count = tiff_unpack(endian, "HHI", data[pos:pos + 8])
        tags[tag] = read_tiff_value(data, base, endian, field_type, value_count, pos + 8)
    return tags


def rational_to_float(value):
    numerator, denominator = value
    return 0.0 if not denominator else numerator / denominator


def exif_gps_to_decimal(gps_tags):
    lat_ref = gps_tags.get(1)
    lat_values = gps_tags.get(2)
    lon_ref = gps_tags.get(3)
    lon_values = gps_tags.get(4)
    if not (lat_ref and lat_values and lon_ref and lon_values):
        return None
    lat = rational_to_float(lat_values[0]) + rational_to_float(lat_values[1]) / 60 + rational_to_float(lat_values[2]) / 3600
    lon = rational_to_float(lon_values[0]) + rational_to_float(lon_values[1]) / 60 + rational_to_float(lon_values[2]) / 3600
    if isinstance(lat_ref, str) and lat_ref.upper().startswith("S"):
        lat *= -1
    if isinstance(lon_ref, str) and lon_ref.upper().startswith("W"):
        lon *= -1
    return lat, lon


def read_jpeg_exif(data):
    if not data.startswith(b"\xff\xd8"):
        return {}
    index = 2
    while index < len(data) - 1:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in (0xD8, 0xD9):
            continue
        if index + 2 > len(data):
            break
        size = struct.unpack(">H", data[index:index + 2])[0]
        if size < 2 or index + size > len(data):
            break
        segment = data[index + 2:index + size]
        index += size
        if marker != 0xE1 or not segment.startswith(b"Exif\x00\x00"):
            continue
        exif = segment[6:]
        if exif[:2] == b"II":
            endian = "I"
        elif exif[:2] == b"MM":
            endian = "M"
        else:
            return {}
        ifd0_offset = tiff_unpack(endian, "I", exif[4:8])[0]
        ifd0 = parse_ifd(exif, 0, ifd0_offset, endian)
        metadata = {}
        exif_ptr = ifd0.get(0x8769)
        gps_ptr = ifd0.get(0x8825)
        if isinstance(exif_ptr, tuple):
            exif_ptr = exif_ptr[0]
        if isinstance(gps_ptr, tuple):
            gps_ptr = gps_ptr[0]
        if exif_ptr:
            exif_tags = parse_ifd(exif, 0, exif_ptr, endian)
            if exif_tags.get(0x9003):
                metadata["datetime"] = exif_tags[0x9003]
            if exif_tags.get(0x0110):
                metadata["camera_model"] = exif_tags[0x0110]
        if gps_ptr:
            gps_tags = parse_ifd(exif, 0, gps_ptr, endian)
            coords = exif_gps_to_decimal(gps_tags)
            if coords:
                metadata["gps"] = coords
        return metadata
    return {}


def read_image_dimensions(file_path):
    with open(file_path, "rb") as handle:
        data = handle.read(131072)
    for reader in (read_png_size, read_gif_size, read_bmp_size, read_webp_size, read_jpeg_size):
        result = reader(data)
        if result:
            return result
    return None


def inspect_media_file(file_path):
    path = Path(file_path)
    stat = path.stat()
    report = {
        "path": str(path),
        "name": path.name,
        "kind": detect_media_kind(file_path),
        "suffix": path.suffix.lower() or "n/a",
        "size_label": format_size(stat.st_size),
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "sha256": file_sha256(file_path),
        "dimensions": None,
        "gps": None,
        "datetime": None,
        "camera_model": None,
    }
    if report["kind"] == "image":
        report["dimensions"] = read_image_dimensions(file_path)
        if path.suffix.lower() in {".jpg", ".jpeg"}:
            exif = read_jpeg_exif(path.read_bytes())
            for key in ("gps", "datetime", "camera_model"):
                report[key] = exif.get(key)
    return report


def ensure_media_preview(file_path, width, height):
    source = Path(file_path)
    if not source.exists():
        return None
    MEDIA_PREVIEW_DIR.mkdir(exist_ok=True)
    stamp = f"{source.resolve()}|{source.stat().st_mtime_ns}|{width}x{height}"
    preview_name = hashlib.sha256(stamp.encode("utf-8")).hexdigest() + ".png"
    preview_path = MEDIA_PREVIEW_DIR / preview_name
    if preview_path.exists():
        return preview_path

    escaped_source = str(source).replace("'", "''")
    escaped_target = str(preview_path).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Drawing; "
        f"$src='{escaped_source}'; $dst='{escaped_target}'; "
        f"$w={int(width)}; $h={int(height)}; "
        "$img=[System.Drawing.Image]::FromFile($src); "
        "$bmp=New-Object System.Drawing.Bitmap($w,$h); "
        "$g=[System.Drawing.Graphics]::FromImage($bmp); "
        "$g.Clear([System.Drawing.Color]::FromArgb(16,35,58)); "
        "$g.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic; "
        "$ratio=[Math]::Max($w / $img.Width, $h / $img.Height); "
        "$drawW=[int]($img.Width * $ratio); $drawH=[int]($img.Height * $ratio); "
        "$x=[int](($w-$drawW)/2); $y=[int](($h-$drawH)/2); "
        "$g.DrawImage($img,$x,$y,$drawW,$drawH); "
        "$img.Dispose(); $g.Dispose(); "
        "$bmp.Save($dst,[System.Drawing.Imaging.ImageFormat]::Png); "
        "$bmp.Dispose()"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode == 0 and preview_path.exists():
            return preview_path
    except Exception:
        return None
    return None


def build_photo_assistant_report(report):
    lines = [
        "PHOTO AI ASSISTANT",
        "",
        f"Файл: {report['name']}",
        f"Тип: {report['kind']}",
        f"Размер: {report['size_label']}",
        f"Изменён: {report['modified']}",
    ]
    if report["dimensions"]:
        lines.append(f"Разрешение: {report['dimensions'][0]} x {report['dimensions'][1]}")
    if report["datetime"]:
        lines.append(f"Время съёмки EXIF: {report['datetime']}")
    if report["camera_model"]:
        lines.append(f"Камера: {report['camera_model']}")
    if report["gps"]:
        lat, lon = report["gps"]
        lines.extend([
            f"GPS: {lat:.6f}, {lon:.6f}",
            "Вывод: точные координаты уже найдены в EXIF, это сильнейшая привязка.",
        ])
    else:
        lines.extend([
            "GPS: не найден",
            "Вывод: нужна визуальная привязка кадра по косвенным признакам.",
        ])
    lines.extend([
        "",
        "Что проверять по кадру:",
        "1. Тени: направление теней и высота солнца помогают сузить время и сторону света.",
        "2. Погода: облачность, снег, мокрый асфальт, сезонность растительности.",
        "3. Архитектура: тип застройки, вывески, язык, номера домов, дорожные знаки.",
        "4. Транспорт: номера, разметка, сторона движения, тип общественного транспорта.",
        "5. Ландшафт: рельеф, линии электропередачи, водоёмы, тип деревьев.",
        "",
        "Как использовать тени:",
        "1. Найди самый длинный контрастный объект: столб, человек, угол здания.",
        "2. Определи, куда направлена тень относительно кадра.",
        "3. Если известна дата съёмки из EXIF, сравни солнце с картой и временем региона.",
        "4. Сверяй направление света с предполагаемой улицей на карте.",
        "",
        "Надёжность:",
        "EXIF GPS > EXIF время > узнаваемые ориентиры > тени и погода.",
        "",
        "Важно:",
        "Это локальный ассистент по метаданным и визуальным чеклистам.",
        "Он не является реальной моделью уровня GeoSpy и не умеет делать точную геолокацию по одному кадру без внешнего AI-сервиса.",
        "",
        f"SHA256: {report['sha256']}",
    ])
    return "\n".join(lines)


def extract_text_from_gemini_response(payload):
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini did not return candidates")
    parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    text = "".join(texts).strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response")
    return text


def _gemini_image_request(file_path, api_key, model_name, prompt_text, response_json_schema=None):
    mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    with open(file_path, "rb") as handle:
        raw = handle.read()
    if len(raw) > 20 * 1024 * 1024:
        raise RuntimeError("Gemini inline image limit is 20 MB. Pick a smaller file.")

    generation_config = {
        "thinkingConfig": {
            "thinkingBudget": -1,
        }
    }
    if response_json_schema:
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseJsonSchema"] = response_json_schema

    payload = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(raw).decode("ascii"),
                    }
                },
                {"text": prompt_text},
            ]
        }],
        "generationConfig": generation_config,
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "User-Agent": MAP_USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    return extract_text_from_gemini_response(response_payload)


def build_gemini_geo_prompt():
    return (
        "You are a senior image geolocation analyst. "
        "Study the image carefully before answering. Use a deliberate internal reasoning process. "
        "Check visible language, road markings, signs, architecture, vegetation, terrain, weather, utilities, vehicles, camera angle, and shadows from the sun. "
        "Do not jump to a fast answer. Build multiple hypotheses, compare them, reject weak ones, then give the strongest final guess. "
        "If the image does not justify a precise location, say so clearly and keep confidence low. "
        "Write a detailed geolocation analysis in plain text with sections: Summary, Best Guess, Search Query, Shadow Analysis, Visual Clues, Candidate Locations, Limitations."
    )


def build_gemini_geo_schema():
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Short conclusion about the most likely location."},
            "confidence": {"type": "number", "description": "0 to 1 confidence for the best guess."},
            "best_guess_label": {"type": "string", "description": "Most likely place label such as city, region, or landmark."},
            "best_guess_query": {"type": "string", "description": "Search query suitable for geocoding."},
            "best_guess_latitude": {"type": ["number", "null"], "description": "Approximate latitude if the model can justify one."},
            "best_guess_longitude": {"type": ["number", "null"], "description": "Approximate longitude if the model can justify one."},
            "shadow_analysis": {"type": "string", "description": "How shadows or sun angle help or do not help."},
            "visible_clues": {"type": "array", "items": {"type": "string"}, "description": "Key visual clues from the image."},
            "candidate_locations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "query": {"type": "string"},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["label", "query", "confidence", "reason"],
                },
            },
            "limitations": {"type": "array", "items": {"type": "string"}, "description": "Why the estimate may be uncertain."},
        },
        "required": [
            "summary",
            "confidence",
            "best_guess_label",
            "best_guess_query",
            "best_guess_latitude",
            "best_guess_longitude",
            "shadow_analysis",
            "visible_clues",
            "candidate_locations",
            "limitations",
        ],
    }


def call_gemini_image_geolocation(file_path, api_key, model_name):
    detailed_analysis = _gemini_image_request(
        file_path,
        api_key,
        model_name,
        build_gemini_geo_prompt(),
    )
    extraction_prompt = (
        "Convert the following geolocation analysis into a JSON object that matches the provided schema. "
        "Preserve uncertainty. If coordinates are not justified, return null for latitude and longitude.\n\n"
        + detailed_analysis
    )
    result_text = _gemini_image_request(
        file_path,
        api_key,
        model_name,
        extraction_prompt,
        response_json_schema=build_gemini_geo_schema(),
    )
    try:
        parsed = json.loads(result_text)
    except json.JSONDecodeError:
        parsed = parse_gemini_text_fallback(detailed_analysis)
    parsed["raw_analysis"] = detailed_analysis
    return parsed


def build_gemini_report(analysis, file_report):
    lines = [
        "GEMINI GEO REPORT",
        "",
        f"Файл: {file_report['name']}",
        f"Итог: {analysis.get('summary', 'n/a')}",
        f"Уверенность: {analysis.get('confidence', 0):.2f}",
        f"Лучшая гипотеза: {analysis.get('best_guess_label', 'n/a')}",
        f"Запрос для карты: {analysis.get('best_guess_query', 'n/a')}",
        "",
        "Тени и солнце:",
        analysis.get("shadow_analysis", "n/a"),
        "",
        "Визуальные признаки:",
    ]
    for clue in analysis.get("visible_clues", [])[:8]:
        lines.append(f"- {clue}")
    lines.extend(["", "Кандидаты:"])
    for candidate in analysis.get("candidate_locations", [])[:5]:
        lines.append(
            f"- {candidate.get('label', 'n/a')} | {candidate.get('confidence', 0):.2f} | {candidate.get('reason', '')}"
        )
    limitations = analysis.get("limitations", [])
    if limitations:
        lines.extend(["", "Ограничения:"])
        for item in limitations[:6]:
            lines.append(f"- {item}")
    raw_analysis = (analysis.get("raw_analysis") or "").strip()
    if raw_analysis:
        lines.extend(["", "Полный ответ Gemini:", raw_analysis])
    lines.extend(["", f"SHA256: {file_report['sha256']}"])
    return "\n".join(lines)


def parse_gemini_text_fallback(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    best_guess = ""
    best_query = ""
    confidence = 0.25
    for line in lines:
        lower = line.lower()
        if not best_guess and ("best guess" in lower or "final guess" in lower or "most likely" in lower):
            best_guess = line.split(":", 1)[-1].strip() if ":" in line else line
        if not best_query and ("search query" in lower or "query" in lower):
            best_query = line.split(":", 1)[-1].strip() if ":" in line else ""
        if "confidence" in lower:
            match = re.search(r"(\d+(?:\.\d+)?)", line)
            if match:
                value = float(match.group(1))
                confidence = value / 100 if value > 1 else value
    if not best_guess and lines:
        best_guess = lines[0]
    if not best_query:
        best_query = best_guess
    clues = lines[:8]
    return {
        "summary": lines[0] if lines else "Gemini returned freeform analysis.",
        "confidence": confidence,
        "best_guess_label": best_guess or "Unknown guess",
        "best_guess_query": best_query or "Unknown place",
        "best_guess_latitude": None,
        "best_guess_longitude": None,
        "shadow_analysis": "See full Gemini response below.",
        "visible_clues": clues,
        "candidate_locations": [{"label": best_guess or "Unknown guess", "query": best_query or "Unknown place", "confidence": confidence, "reason": "Recovered from freeform Gemini response."}],
        "limitations": ["Gemini did not return structured JSON; fallback parser was used."],
        "raw_analysis": text,
    }


class StatCard(tk.Frame):
    def __init__(self, master, title, value_var, accent):
        super().__init__(master, bg=CARD, padx=18, pady=16)
        tk.Label(self, text=title, bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")
        row = tk.Frame(self, bg=CARD)
        row.pack(fill=X, pady=(10, 0))
        tk.Label(row, textvariable=value_var, bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 18)).pack(side=LEFT)
        dot = Canvas(row, width=16, height=16, bg=CARD, highlightthickness=0)
        dot.pack(side=RIGHT, pady=4)
        dot.create_oval(1, 1, 15, 15, fill=accent, outline="")


class SidebarButton(Canvas):
    def __init__(self, master, text, description, command):
        super().__init__(master, width=224, height=74, bg=PANEL, highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.active = False
        self.shape = round_rect(self, 4, 6, 220, 70, radius=22, fill=PANEL)
        self.title = self.create_text(18, 26, text=text, anchor="w", fill=TEXT, font=("Segoe UI Semibold", 12))
        self.desc = self.create_text(18, 49, text=description, anchor="w", fill=MUTED, font=("Segoe UI", 9))
        self.bind("<Button-1>", lambda _: self.command())
        self.bind("<Enter>", self._hover_on)
        self.bind("<Leave>", self._hover_off)

    def set_active(self, active):
        self.active = active
        self.itemconfigure(self.shape, fill=CARD_ALT if active else PANEL)
        self.itemconfigure(self.desc, fill="#c8d4e5" if active else MUTED)

    def _hover_on(self, _):
        if not self.active:
            self.itemconfigure(self.shape, fill="#123051")
            self.itemconfigure(self.desc, fill=TEXT)

    def _hover_off(self, _):
        if not self.active:
            self.itemconfigure(self.shape, fill=PANEL)
            self.itemconfigure(self.desc, fill=MUTED)


class RoundedButton(Canvas):
    def __init__(self, master, text, command, fill, text_fill, width=152, height=42):
        super().__init__(master, width=width, height=height, bg=master.cget("bg"), highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.fill = fill
        self.text_fill = text_fill
        self.shape = round_rect(self, 4, 4, width - 4, height - 4, radius=18, fill=fill)
        self.label = self.create_text(width / 2, height / 2, text=text, fill=text_fill, font=("Segoe UI Semibold", 10))
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._hover_on)
        self.bind("<Leave>", self._hover_off)

    def _click(self, _):
        self.command()

    def _hover_on(self, _):
        self.itemconfigure(self.shape, fill=CARD_SOFT if self.fill not in (ACCENT, ACCENT_2, ACCENT_3) else self.fill)

    def _hover_off(self, _):
        self.itemconfigure(self.shape, fill=self.fill)


class RealMapCanvas(Canvas):
    def __init__(self, master, info_var):
        super().__init__(master, bg=EARTH, highlightthickness=0, bd=0)
        self.info_var = info_var
        self.zoom = 3
        self.center_lat = 20.0
        self.center_lon = 0.0
        self.last_drag = None
        self.markers = []
        self.tile_cache = {}
        self.tile_loading = set()
        self._image_refs = []
        self.bind("<Configure>", lambda _: self.redraw())
        self.bind("<Button-1>", self.add_marker)
        self.bind("<Button-3>", self.start_pan)
        self.bind("<B3-Motion>", self.pan)
        self.bind("<ButtonRelease-3>", self.stop_pan)
        self.bind("<MouseWheel>", self.on_wheel)

    def redraw(self):
        self.delete("all")
        self._image_refs.clear()
        width = max(self.winfo_width(), 10)
        height = max(self.winfo_height(), 10)
        self.create_rectangle(0, 0, width, height, fill=EARTH, outline="")

        center_world_x, center_world_y = latlon_to_world(self.center_lat, self.center_lon, self.zoom)
        top_left_x = center_world_x - width / 2
        top_left_y = center_world_y - height / 2
        tile_count = 2 ** self.zoom
        first_tile_x = int(math.floor(top_left_x / MAP_TILE_SIZE))
        first_tile_y = int(math.floor(top_left_y / MAP_TILE_SIZE))
        tiles_x = width // MAP_TILE_SIZE + 3
        tiles_y = height // MAP_TILE_SIZE + 3

        for tile_x in range(first_tile_x, first_tile_x + tiles_x):
            wrapped_x = tile_x % tile_count
            screen_x = tile_x * MAP_TILE_SIZE - top_left_x
            for tile_y in range(first_tile_y, first_tile_y + tiles_y):
                if 0 <= tile_y < tile_count:
                    screen_y = tile_y * MAP_TILE_SIZE - top_left_y
                    self._draw_tile(wrapped_x, tile_y, screen_x, screen_y)

        for marker in self.markers:
            self._draw_marker(marker["lat"], marker["lon"], marker["title"])

        self.create_text(16, 14, anchor="w", fill=TEXT, font=("Segoe UI", 10), text="ЛКМ: метка   ПКМ + drag: движение   Колесо: масштаб")

    def _draw_tile(self, x, y, screen_x, screen_y):
        key = (self.zoom, x, y)
        image = self.tile_cache.get(key)
        if image is None:
            self.create_rectangle(screen_x, screen_y, screen_x + MAP_TILE_SIZE, screen_y + MAP_TILE_SIZE, fill="#10213d", outline="#173056")
            if key not in self.tile_loading:
                self.tile_loading.add(key)
                threading.Thread(target=self._load_tile, args=key, daemon=True).start()
            return
        self._image_refs.append(image)
        self.create_image(screen_x, screen_y, anchor="nw", image=image)

    def _load_tile(self, zoom, x, y):
        url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
        try:
            raw = fetch_bytes(url, timeout=8)
            encoded = base64.b64encode(raw).decode("ascii")
            self.after(0, lambda: self._store_tile((zoom, x, y), encoded))
        except Exception:
            self.after(0, lambda: self.tile_loading.discard((zoom, x, y)))

    def _store_tile(self, key, encoded):
        try:
            self.tile_cache[key] = tk.PhotoImage(data=encoded)
        finally:
            self.tile_loading.discard(key)
            self.redraw()

    def _screen_to_latlon(self, x, y):
        width = max(self.winfo_width(), 10)
        height = max(self.winfo_height(), 10)
        center_world_x, center_world_y = latlon_to_world(self.center_lat, self.center_lon, self.zoom)
        return world_to_latlon(center_world_x + (x - width / 2), center_world_y + (y - height / 2), self.zoom)

    def _latlon_to_screen(self, lat, lon):
        width = max(self.winfo_width(), 10)
        height = max(self.winfo_height(), 10)
        center_world_x, center_world_y = latlon_to_world(self.center_lat, self.center_lon, self.zoom)
        world_x, world_y = latlon_to_world(lat, lon, self.zoom)
        return width / 2 + (world_x - center_world_x), height / 2 + (world_y - center_world_y)

    def _draw_marker(self, lat, lon, title):
        x, y = self._latlon_to_screen(lat, lon)
        self.create_oval(x - 7, y - 7, x + 7, y + 7, fill=ACCENT, outline="")
        self.create_text(x + 14, y - 12, anchor="w", text=title, fill=TEXT, font=("Segoe UI", 9))

    def add_marker(self, event):
        lat, lon = self._screen_to_latlon(event.x, event.y)
        self.markers.append({"lat": lat, "lon": lon, "title": f"Метка {len(self.markers) + 1}"})
        self.info_var.set(f"Метка поставлена: {lat:.5f}, {lon:.5f}")
        self.redraw()

    def add_geo_marker(self, lat, lon, title="Search"):
        self.markers.append({"lat": lat, "lon": lon, "title": title})
        self.focus_on(lat, lon, max(self.zoom, 14))
        self.info_var.set(f"Метка добавлена: {lat:.5f}, {lon:.5f}")

    def clear_markers(self):
        self.markers.clear()
        self.redraw()

    def fly_to(self, lat, lon):
        start_lat = self.center_lat
        start_lon = self.center_lon
        target_lat = clamp_lat(lat)
        target_lon = clamp_lon(lon)
        for step in range(1, 19):
            t = step / 18
            ease = 1 - (1 - t) ** 2
            self.after(step * 16, lambda e=ease: self._set_center(start_lat + (target_lat - start_lat) * e, start_lon + (target_lon - start_lon) * e))

    def focus_on(self, lat, lon, zoom=None):
        if zoom is not None:
            self.zoom = max(MAP_MIN_ZOOM, min(MAP_MAX_ZOOM, zoom))
        self.fly_to(lat, lon)

    def _set_center(self, lat, lon):
        self.center_lat = clamp_lat(lat)
        self.center_lon = clamp_lon(lon)
        self.redraw()

    def start_pan(self, event):
        self.last_drag = (event.x, event.y)

    def pan(self, event):
        if not self.last_drag:
            return
        dx = event.x - self.last_drag[0]
        dy = event.y - self.last_drag[1]
        center_world_x, center_world_y = latlon_to_world(self.center_lat, self.center_lon, self.zoom)
        self.center_lat, self.center_lon = world_to_latlon(center_world_x - dx, center_world_y - dy, self.zoom)
        self.last_drag = (event.x, event.y)
        self.redraw()

    def stop_pan(self, _):
        self.last_drag = None

    def on_wheel(self, event):
        new_zoom = self.zoom + 1 if event.delta > 0 else self.zoom - 1
        new_zoom = max(MAP_MIN_ZOOM, min(MAP_MAX_ZOOM, new_zoom))
        if new_zoom == self.zoom:
            return
        self.center_lat, self.center_lon = self._screen_to_latlon(event.x, event.y)
        self.zoom = new_zoom
        self.redraw()

    def open_in_browser(self):
        webbrowser.open(f"https://www.google.com/maps/@{self.center_lat:.6f},{self.center_lon:.6f},12z")


class NodeCanvas(Canvas):
    def __init__(self, master, on_select):
        super().__init__(master, bg=EARTH, highlightthickness=0, bd=0)
        self.on_select = on_select
        self.nodes = {}
        self.edges = []
        self.selected_node_id = None
        self.dragging_node_id = None
        self.drag_offset = (0, 0)
        self.linking_node_id = None
        self.link_preview = None
        self.scale = 1.0
        self.grid_step = 40
        self.media_cache = {}
        self.bind("<Button-1>", self._click_canvas)
        self.bind("<B1-Motion>", self._drag_selected)
        self.bind("<ButtonRelease-1>", self._release_drag)
        self.bind("<Button-3>", self._start_link)
        self.bind("<B3-Motion>", self._preview_link)
        self.bind("<ButtonRelease-3>", self._finish_link)
        self.bind("<MouseWheel>", self._zoom_grid)

    def set_nodes(self, nodes, edges):
        self.nodes = nodes
        self.edges = edges
        self.redraw()

    def redraw(self):
        self.delete("all")
        width = max(self.winfo_width(), 10)
        height = max(self.winfo_height(), 10)
        step = max(20, int(self.grid_step * self.scale))
        for x in range(0, width, step):
            self.create_line(x, 0, x, height, fill="#0d1e31")
        for y in range(0, height, step):
            self.create_line(0, y, width, y, fill="#0d1e31")
        for source_id, target_id in self.edges:
            source = self.nodes.get(source_id)
            target = self.nodes.get(target_id)
            if not source or not target:
                continue
            sx, sy, sw, sh = self._node_rect(source)
            tx, ty, tw, th = self._node_rect(target)
            self.create_line(sx + sw / 2, sy + sh / 2, tx + tw / 2, ty + th / 2, fill=NODE_LINE, width=3, smooth=True)
        for node in self.nodes.values():
            self._draw_node(node)
        if self.link_preview:
            source = self.nodes.get(self.linking_node_id)
            if source:
                sx, sy, sw, sh = self._node_rect(source)
                x1, y1, x2, y2 = self.link_preview
                self.create_line(sx + sw / 2, sy + sh / 2, x2, y2, fill=ACCENT_3, dash=(6, 4), width=2)

    def _draw_node(self, node):
        x, y, width, height = self._node_rect(node)
        fill = NODE_ACTIVE if node.node_id == self.selected_node_id else NODE_FILL
        outline = ACCENT if node.node_id == self.selected_node_id else ""
        round_rect(self, x, y, x + width, y + height, radius=max(14, int(20 * self.scale)), fill=fill, outline=outline)
        if node.node_type == "media" and node.media_path:
            self._draw_media_background(node, x, y, width, height)
        self.create_text(x + 14 * self.scale, y + 18 * self.scale, anchor="w", text=node.title or "Без названия", fill=TEXT, font=("Segoe UI Semibold", max(9, int(12 * self.scale))))
        if node.node_type == "text":
            preview = (node.body or "Пустой узел").strip().replace("\n", " ")
            if len(preview) > 80:
                preview = preview[:77] + "..."
            self.create_text(
                x + 14 * self.scale,
                y + 44 * self.scale,
                anchor="nw",
                text=preview,
                fill=MUTED,
                width=max(120, width - 28 * self.scale),
                font=("Segoe UI", max(8, int(10 * self.scale))),
            )
        else:
            media_name = Path(node.media_path).name if node.media_path else "media"
            self.create_text(
                x + width / 2,
                y + height - 18 * self.scale,
                text=media_name,
                fill=TEXT,
                width=max(120, width - 24 * self.scale),
                font=("Segoe UI", max(8, int(9 * self.scale))),
            )
        self.create_text(x + 14 * self.scale, y + height - 16 * self.scale, anchor="w", text=f"ID: {node.node_id}", fill=ACCENT_3, font=("Segoe UI", max(8, int(9 * self.scale))))

    def _draw_media_background(self, node, x, y, width, height):
        image = self._get_media_preview(node.media_path)
        if image:
            self.create_image(x + width / 2, y + height / 2, image=image)
        else:
            self.create_rectangle(x + 8, y + 28, x + width - 8, y + height - 8, fill="#284766", outline="")

    def _get_media_preview(self, media_path):
        if not media_path or not os.path.exists(media_path):
            return None
        preview_width = max(120, int(224 * self.scale))
        preview_height = max(70, int(88 * self.scale))
        source_for_photo = Path(media_path)
        preview_path = ensure_media_preview(media_path, preview_width, preview_height)
        if preview_path:
            source_for_photo = preview_path
        elif Path(media_path).suffix.lower() not in {".png", ".gif"}:
            return None
        key = (str(source_for_photo), round(self.scale, 1))
        if key in self.media_cache:
            return self.media_cache[key]
        try:
            image = tk.PhotoImage(file=str(source_for_photo))
            self.media_cache[key] = image
            return image
        except Exception:
            return None

    def _node_rect(self, node):
        width = 240 * self.scale
        height = 116 * self.scale
        return node.x * self.scale, node.y * self.scale, width, height

    def _hit_test(self, x, y):
        for node in reversed(list(self.nodes.values())):
            nx, ny, width, height = self._node_rect(node)
            if nx <= x <= nx + width and ny <= y <= ny + height:
                return node.node_id
        return None

    def _click_canvas(self, event):
        clicked_id = self._hit_test(event.x, event.y)
        if clicked_id is not None:
            node = self.nodes[clicked_id]
            nx, ny, _, _ = self._node_rect(node)
            self.dragging_node_id = node.node_id
            self.drag_offset = (event.x - nx, event.y - ny)
        self.selected_node_id = clicked_id
        self.redraw()
        self.on_select(clicked_id)

    def _drag_selected(self, event):
        if self.dragging_node_id is None:
            return
        node = self.nodes.get(self.dragging_node_id)
        if not node:
            return
        node.x = max(12, (event.x - self.drag_offset[0]) / self.scale)
        node.y = max(12, (event.y - self.drag_offset[1]) / self.scale)
        self.redraw()
        self.on_select(node.node_id, drag_update=True)

    def _release_drag(self, _):
        self.dragging_node_id = None

    def _start_link(self, event):
        source_id = self._hit_test(event.x, event.y)
        if source_id is None:
            return
        self.linking_node_id = source_id
        self.link_preview = (event.x, event.y, event.x, event.y)
        self.selected_node_id = source_id
        self.on_select(source_id)
        self.redraw()

    def _preview_link(self, event):
        if self.linking_node_id is None:
            return
        self.link_preview = (0, 0, event.x, event.y)
        self.redraw()

    def _finish_link(self, event):
        if self.linking_node_id is None:
            return
        target_id = self._hit_test(event.x, event.y)
        source_id = self.linking_node_id
        self.linking_node_id = None
        self.link_preview = None
        self.redraw()
        if target_id is not None and target_id != source_id:
            self.on_select(source_id, link_target=target_id)

    def _zoom_grid(self, event):
        self.scale += 0.1 if event.delta > 0 else -0.1
        self.scale = max(0.6, min(1.8, self.scale))
        self.redraw()


class SchizoOsintApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1520x920")
        self.root.minsize(1240, 780)
        self.root.configure(bg=BG)

        self.stats = load_stats()
        self.stats["launches"] += 1
        self.stats["last_opened"] = datetime.now().isoformat(timespec="seconds")
        save_stats(self.stats)

        self.info_vars = {
            "device": StringVar(value=platform.node() or "Unknown"),
            "local_ip": StringVar(value=get_local_ip()),
            "public_ip": StringVar(value="Загрузка..."),
            "latency": StringVar(value="Проверка..."),
            "ram": StringVar(value=get_total_memory()),
            "launches": StringVar(value=str(self.stats["launches"])),
        }
        self.online_var = StringVar(value="Онлайн: недоступно без сервера")
        self.geo_status = StringVar(value="Готово к поиску")
        self.node_status = StringVar(value="Создайте первый узел")
        self.search_var = StringVar(value="")
        self.node_title_var = StringVar(value="")
        self.node_link_to_var = StringVar(value="")
        self.node_catalog_var = StringVar(value="Узлов пока нет")
        self.node_type_var = StringVar(value="text")

        self.analysis_box = None
        self.map_canvas = None
        self.node_text = None
        self.node_canvas = None
        self.tab_frames = {}
        self.nav_buttons = {}

        self.nodes = {}
        self.node_edges = []
        self.next_node_id = 1
        self.selected_node_id = None

        self._build_shell()
        self._build_dashboard_tab()
        self._build_geoint_tab()
        self._build_nodes_tab()
        self.show_tab("Dashboard")
        self._refresh_network_async()

    def _build_shell(self):
        self.sidebar = tk.Frame(self.root, bg=PANEL, width=256)
        self.sidebar.pack(side=LEFT, fill=Y)
        self.sidebar.pack_propagate(False)

        brand = Canvas(self.sidebar, width=224, height=144, bg=PANEL, highlightthickness=0, bd=0)
        brand.pack(padx=16, pady=(18, 12))
        round_rect(brand, 4, 6, 220, 140, radius=28, fill=CARD_ALT)
        brand.create_text(20, 34, text=APP_NAME, anchor="w", fill=TEXT, font=("Segoe UI Semibold", 18))
        brand.create_text(20, 64, text="OSINT workspace", anchor="w", fill=MUTED, font=("Segoe UI", 11))
        brand.create_text(20, 94, text="Карта, фото и узлы", anchor="w", fill=ACCENT, font=("Segoe UI Semibold", 11))
        brand.create_text(20, 120, text="Все функции разнесены по экранам", anchor="w", fill=MUTED, font=("Segoe UI", 9))

        nav = tk.Frame(self.sidebar, bg=PANEL)
        nav.pack(fill=X, padx=16, pady=8)
        for name, desc in (
            ("Dashboard", "система и сети"),
            ("GEOINT", "карта и геопоиск"),
            ("Nodes", "узлы, связи и вложения"),
        ):
            button = SidebarButton(nav, name, desc, lambda tab_name=name: self.show_tab(tab_name))
            button.pack(pady=6)
            self.nav_buttons[name] = button

        footer = tk.Frame(self.sidebar, bg=PANEL)
        footer.pack(side=BOTTOM, fill=X, padx=18, pady=20)
        tk.Label(footer, text="Социальные сети", fg=MUTED, bg=PANEL, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 6))
        self._make_link(footer, "Telegram", TG_LINK)
        self._make_link(footer, "Discord", DISCORD_LINK)
        tk.Label(footer, textvariable=self.online_var, fg=ACCENT_3, bg=PANEL, wraplength=210, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(14, 0))
        tk.Label(footer, text=APP_FOOTER, fg=MUTED, bg=PANEL, font=("Segoe UI", 9)).pack(anchor="w", pady=(14, 0))

        self.content = tk.Frame(self.root, bg=BG)
        self.content.pack(side=RIGHT, fill=BOTH, expand=True)

    def _make_link(self, parent, label, url):
        link = tk.Label(parent, text=label, fg=ACCENT, bg=PANEL, cursor="hand2", font=("Segoe UI Semibold", 11))
        link.pack(anchor="w", pady=2)
        link.bind("<Button-1>", lambda _: webbrowser.open(url))

    def _register_tab(self, name):
        frame = tk.Frame(self.content, bg=BG)
        self.tab_frames[name] = frame
        return frame

    def show_tab(self, name):
        for tab_name, frame in self.tab_frames.items():
            if tab_name == name:
                frame.pack(fill=BOTH, expand=True)
            else:
                frame.pack_forget()
        for tab_name, button in self.nav_buttons.items():
            button.set_active(tab_name == name)

    def _build_header(self, parent, title, description, badge):
        header = tk.Frame(parent, bg=CARD_ALT, padx=24, pady=18)
        header.pack(fill=X, padx=24, pady=(18, 12))
        top = tk.Frame(header, bg=CARD_ALT)
        top.pack(fill=X)
        tk.Label(top, text=title, bg=CARD_ALT, fg=TEXT, font=("Segoe UI Semibold", 28)).pack(side=LEFT)
        tk.Label(top, text=badge, bg=CARD_ALT, fg=ACCENT, font=("Segoe UI Semibold", 11)).pack(side=RIGHT, pady=8)
        tk.Label(header, text=description, bg=CARD_ALT, fg=MUTED, font=("Segoe UI", 11), justify="left").pack(anchor="w", pady=(8, 0))

    def _action_button(self, parent, text, command, color):
        button = RoundedButton(parent, text, command, color, BG, width=300, height=46)
        button.pack(fill=X, pady=(14, 0))

    def _small_button(self, parent, text, command, color):
        fg = BG if color in (ACCENT, ACCENT_2, ACCENT_3) else TEXT
        return RoundedButton(parent, text, command, color, fg)

    def _build_dashboard_tab(self):
        frame = self._register_tab("Dashboard")
        self._build_header(frame, "Dashboard", "Стартовый экран. Здесь видно состояние устройства и сети, без блока быстрого доступа к функциям.", "Overview")

        stats = tk.Frame(frame, bg=BG)
        stats.pack(fill=X, padx=24, pady=8)
        cards = [
            ("Устройство", self.info_vars["device"], ACCENT),
            ("Локальный IP", self.info_vars["local_ip"], ACCENT_2),
            ("Публичный IP", self.info_vars["public_ip"], ACCENT_3),
            ("Задержка", self.info_vars["latency"], ACCENT),
            ("ОЗУ", self.info_vars["ram"], ACCENT_2),
            ("Запуски", self.info_vars["launches"], ACCENT_3),
        ]
        for title, var, accent in cards:
            StatCard(stats, title, var, accent).pack(side=LEFT, fill=X, expand=True, padx=(0, 12))

        body = tk.Frame(frame, bg=BG)
        body.pack(fill=BOTH, expand=True, padx=24, pady=12)
        left = tk.Frame(body, bg=CARD, padx=20, pady=18)
        left.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 12))
        right = tk.Frame(body, bg=CARD, padx=20, pady=18, width=360)
        right.pack(side=RIGHT, fill=Y)
        right.pack_propagate(False)

        tk.Label(left, text="Снимок системы", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 18)).pack(anchor="w")
        snapshot = f"Платформа: {platform.platform()}\nPython: {platform.python_version()}\nCPU cores: {os.cpu_count()}\nHostname: {socket.gethostname()}\nПоследний запуск: {self.stats['last_opened']}"
        tk.Label(left, text=snapshot, bg=CARD, fg=MUTED, justify="left", font=("Consolas", 11)).pack(anchor="w", pady=(14, 18))
        tips = "Что где:\n1. GEOINT: адреса, IP и координаты.\n2. Nodes: текстовые и медиа-узлы, связи и редактирование."
        tk.Label(left, text=tips, bg=CARD, fg=TEXT, justify="left", font=("Segoe UI", 11)).pack(anchor="w")

        tk.Label(right, text="Социальные сети", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 18)).pack(anchor="w")
        self._action_button(right, "Открыть Telegram", lambda: webbrowser.open(TG_LINK), ACCENT)
        self._action_button(right, "Открыть Discord", lambda: webbrowser.open(DISCORD_LINK), ACCENT_2)
        note = "Переходы по функциям убраны из этого блока. Вкладки сверху слева остаются основным способом навигации."
        tk.Label(right, text=note, bg=CARD, fg=MUTED, justify="left", wraplength=300, font=("Segoe UI", 10)).pack(anchor="w", pady=(18, 0))

    def _build_geoint_tab(self):
        frame = self._register_tab("GEOINT")
        self._build_header(frame, "GEOINT", "Поиск по адресу, IP и координатам. Без фото и ИИ, только три понятных режима поиска.", "Map Search")

        split = tk.Frame(frame, bg=BG)
        split.pack(fill=BOTH, expand=True, padx=24, pady=12)
        left = tk.Frame(split, bg=CARD)
        left.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 12))
        right_host = tk.Frame(split, bg=CARD, width=430)
        right_host.pack(side=RIGHT, fill=Y)
        right_host.pack_propagate(False)

        self.map_canvas = RealMapCanvas(left, self.geo_status)
        self.map_canvas.pack(fill=BOTH, expand=True, padx=2, pady=2)

        right_canvas = tk.Canvas(right_host, bg=CARD, highlightthickness=0, bd=0, width=450)
        right_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        right_scroll = tk.Scrollbar(right_host, orient="vertical", command=right_canvas.yview)
        right_scroll.pack(side=RIGHT, fill=Y)
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right = tk.Frame(right_canvas, bg=CARD, padx=18, pady=18)
        right_window = right_canvas.create_window((0, 0), window=right, anchor="nw")

        def _sync_right_panel(_=None):
            right_canvas.configure(scrollregion=right_canvas.bbox("all"))
            right_canvas.itemconfigure(right_window, width=right_canvas.winfo_width())

        right.bind("<Configure>", _sync_right_panel)
        right_canvas.bind("<Configure>", _sync_right_panel)
        right_canvas.bind_all(
            "<MouseWheel>",
            lambda event: right_canvas.yview_scroll(-1 * int(event.delta / 120), "units")
            if right_canvas.winfo_exists() else None,
        )

        tk.Label(right, text="Поиск точки", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(right, text="Адрес, IP или координаты", bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 8))
        search_entry = tk.Entry(right, textvariable=self.search_var, bg="#0d1729", fg=TEXT, insertbackground=TEXT, relief="flat", font=("Consolas", 11))
        search_entry.pack(fill=X, ipady=9)
        search_entry.bind("<Return>", lambda _: self.search_location())

        buttons = tk.Frame(right, bg=CARD)
        buttons.pack(fill=X, pady=12)
        self._small_button(buttons, "Найти", self.search_location, ACCENT).pack(side=LEFT)
        self._small_button(buttons, "Очистить метки", self.map_canvas.clear_markers, "#2c4c67").pack(side=LEFT, padx=8)
        self._small_button(buttons, "Google Maps", self.map_canvas.open_in_browser, "#2c4c67").pack(side=LEFT)

        tk.Label(right, text="Результат поиска", bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(14, 6))
        analysis_wrap = tk.Frame(right, bg="#0d1729")
        analysis_wrap.pack(fill=X)
        analysis_scroll = tk.Scrollbar(analysis_wrap)
        analysis_scroll.pack(side=RIGHT, fill=Y)
        self.analysis_box = Text(analysis_wrap, height=8, bg="#0d1729", fg=TEXT, insertbackground=TEXT, relief="flat", font=("Consolas", 10), padx=10, pady=10, wrap="word", yscrollcommand=analysis_scroll.set)
        self.analysis_box.pack(side=LEFT, fill=X, expand=True)
        analysis_scroll.config(command=self.analysis_box.yview)
        self.analysis_box.insert("1.0", "Что умеет экран:\n- искать адреса\n- определять примерную точку по IP\n- принимать координаты")
        guide = (
            "Примеры:\n"
            "1. Адрес: Kyiv, Khreshchatyk 1\n"
            "2. IP: 8.8.8.8\n"
            "3. Координаты: 50.4501, 30.5234"
        )
        tk.Label(right, text=guide, bg=CARD, fg=MUTED, justify="left", wraplength=380, font=("Segoe UI", 10)).pack(anchor="w", pady=(14, 0))
        tk.Label(right, textvariable=self.geo_status, bg=CARD, fg=WARN, wraplength=380, justify="left", font=("Segoe UI", 10)).pack(anchor="w", pady=(14, 0))

    def _build_nodes_tab(self):
        frame = self._register_tab("Nodes")
        self._build_header(frame, "Nodes", "Текстовые и медиа-узлы. Колесо меняет масштаб сетки, ЛКМ двигает, ПКМ тянет связь от родителя к дочернему узлу.", "Visual Board")

        split = tk.Frame(frame, bg=BG)
        split.pack(fill=BOTH, expand=True, padx=24, pady=12)
        left = tk.Frame(split, bg=CARD, padx=18, pady=18)
        left.pack(side=LEFT, fill=Y, padx=(0, 12))
        right = tk.Frame(split, bg=CARD)
        right.pack(side=RIGHT, fill=BOTH, expand=True)

        tk.Label(left, text="Редактор узла", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(left, text="Тип выбранного узла", bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(10, 6))
        tk.Label(left, textvariable=self.node_type_var, bg="#0d1729", fg=TEXT, anchor="w", font=("Consolas", 10), padx=10, pady=10).pack(fill=X)
        tk.Label(left, text="Название", bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(12, 6))
        tk.Entry(left, textvariable=self.node_title_var, bg="#0d1729", fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 11)).pack(fill=X, ipady=8)
        tk.Label(left, text="Текст узла", bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(12, 6))
        self.node_text = Text(left, height=9, bg="#0d1729", fg=TEXT, insertbackground=TEXT, relief="flat", font=("Consolas", 10), padx=10, pady=10)
        self.node_text.pack(fill=X)

        action_row = tk.Frame(left, bg=CARD)
        action_row.pack(fill=X, pady=12)
        self._small_button(action_row, "Текстовый узел", self.create_text_node, ACCENT).pack(side=LEFT)
        self._small_button(action_row, "Медиа-узел", self.create_media_node, ACCENT_3).pack(side=LEFT, padx=8)
        save_row = tk.Frame(left, bg=CARD)
        save_row.pack(fill=X, pady=(0, 12))
        self._small_button(save_row, "Сохранить правки", self.save_current_node, ACCENT_2).pack(side=LEFT)
        self._small_button(save_row, "Удалить узел", self.delete_current_node, "#7b3247").pack(side=LEFT, padx=8)
        self._small_button(save_row, "Открыть медиа", self.open_selected_node_media, "#2c4c67").pack(side=LEFT)

        hint = (
            "Управление:\n"
            "1. ЛКМ по узлу - выбрать и двигать.\n"
            "2. ПКМ от одного узла к другому - создать родительскую связь.\n"
            "3. Колесо мыши - увеличить или уменьшить сетку."
        )
        tk.Label(left, text=hint, bg=CARD, fg=MUTED, justify="left", wraplength=310, font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))
        tk.Label(left, text="Список узлов", bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(12, 6))
        tk.Label(left, textvariable=self.node_catalog_var, bg="#0d1729", fg=TEXT, justify="left", wraplength=310, font=("Consolas", 9), padx=10, pady=10).pack(fill=X)
        tk.Label(left, textvariable=self.node_status, bg=CARD, fg=WARN, wraplength=310, justify="left", font=("Segoe UI", 10)).pack(anchor="w", pady=(12, 0))

        self.node_canvas = NodeCanvas(right, self.select_node)
        self.node_canvas.pack(fill=BOTH, expand=True, padx=2, pady=2)
        self.node_canvas.bind("<Configure>", lambda _: self.node_canvas.redraw())

    def select_file(self):
        return filedialog.askopenfilename(
            title="Выберите медиафайл",
            filetypes=[
                ("Media files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.mp4 *.mov *.avi *.mkv *.webm *.mp3 *.wav"),
                ("All files", "*.*"),
            ],
        )

    def search_location(self):
        query = self.search_var.get().strip()
        if not query:
            self.geo_status.set("Введите адрес, IP или координаты")
            return
        self.geo_status.set("Идёт поиск местоположения...")
        threading.Thread(target=self._search_location_worker, args=(query,), daemon=True).start()

    def _search_location_worker(self, query):
        try:
            result = resolve_location(query)
            self.root.after(0, lambda: self._apply_search_result(result))
        except Exception as error:
            self.root.after(0, lambda: self._search_failed(str(error)))

    def _apply_search_result(self, result):
        self.map_canvas.add_geo_marker(result["lat"], result["lon"], "Search")
        self.analysis_box.delete("1.0", "end")
        self.analysis_box.insert("1.0", "\n".join([
            f"KIND: {result['kind']}",
            f"LABEL: {result['label']}",
            f"LAT: {result['lat']:.6f}",
            f"LON: {result['lon']:.6f}",
            f"DETAILS: {result['details']}",
        ]))
        self.geo_status.set(f"Найдено: {result['label']}")

    def _search_failed(self, message):
        self.geo_status.set("Поиск не удался")
        self.analysis_box.delete("1.0", "end")
        self.analysis_box.insert("1.0", f"ERROR: {message}")

    def _refresh_node_catalog(self):
        if not self.nodes:
            self.node_catalog_var.set("Узлов пока нет")
            return
        lines = []
        for node in self.nodes.values():
            label = "media" if node.node_type == "media" else "text"
            lines.append(f"{node.node_id}: [{label}] {node.title or 'Без названия'}")
        self.node_catalog_var.set("\n".join(lines))

    def create_text_node(self):
        node_id = self.next_node_id
        self.next_node_id += 1
        x = 40 + ((node_id - 1) % 4) * 260
        y = 40 + ((node_id - 1) // 4) * 140
        self.nodes[node_id] = NodeItem(node_id=node_id, node_type="text", title=f"Узел {node_id}", body="", x=x, y=y)
        self._refresh_node_catalog()
        self.node_canvas.set_nodes(self.nodes, self.node_edges)
        self.select_node(node_id)
        self.node_status.set(f"Создан текстовый узел {node_id}")

    def create_media_node(self):
        file_path = self.select_file()
        if not file_path:
            return
        node_id = self.next_node_id
        self.next_node_id += 1
        x = 40 + ((node_id - 1) % 4) * 260
        y = 40 + ((node_id - 1) // 4) * 140
        self.nodes[node_id] = NodeItem(
            node_id=node_id,
            node_type="media",
            title=Path(file_path).stem or f"Media {node_id}",
            body="",
            x=x,
            y=y,
            media_path=file_path,
        )
        self._refresh_node_catalog()
        self.node_canvas.set_nodes(self.nodes, self.node_edges)
        self.select_node(node_id)
        self.node_status.set(f"Создан медиа-узел {node_id}")

    def select_node(self, node_id, drag_update=False, link_target=None):
        if link_target is not None and node_id is not None:
            self._create_link(node_id, link_target)
            return
        self.selected_node_id = node_id
        self.node_canvas.selected_node_id = node_id
        if drag_update:
            self.node_canvas.redraw()
            return
        self.node_text.configure(state="normal")
        if node_id is None:
            self.node_title_var.set("")
            self.node_type_var.set("none")
            self.node_text.delete("1.0", "end")
            self.node_status.set("Узел не выбран")
            self.node_canvas.redraw()
            return
        node = self.nodes.get(node_id)
        if not node:
            return
        self.node_type_var.set(node.node_type)
        self.node_title_var.set(node.title)
        self.node_text.delete("1.0", "end")
        self.node_text.insert("1.0", node.body or "")
        self.node_text.configure(state="normal" if node.node_type == "text" else "disabled")
        self.node_status.set(f"Выбран узел {node_id}. Можно менять текст, медиа и связи.")
        self.node_canvas.redraw()

    def save_current_node(self):
        if self.selected_node_id is None:
            self.node_status.set("Сначала выберите или создайте узел")
            return
        node = self.nodes.get(self.selected_node_id)
        if not node:
            return
        node.title = self.node_title_var.get().strip() or f"Узел {node.node_id}"
        if node.node_type == "text":
            node.body = self.node_text.get("1.0", "end").strip()
        self._refresh_node_catalog()
        self.node_canvas.redraw()
        self.node_status.set(f"Узел {node.node_id} сохранён")

    def delete_current_node(self):
        if self.selected_node_id is None:
            self.node_status.set("Нет выбранного узла")
            return
        node_id = self.selected_node_id
        self.nodes.pop(node_id, None)
        self.node_edges = [edge for edge in self.node_edges if node_id not in edge]
        self.selected_node_id = None
        self.node_canvas.selected_node_id = None
        self._refresh_node_catalog()
        self.node_canvas.set_nodes(self.nodes, self.node_edges)
        self.select_node(None)
        self.node_status.set(f"Узел {node_id} удалён")

    def open_selected_node_media(self):
        if self.selected_node_id is None:
            self.node_status.set("Сначала выберите узел")
            return
        node = self.nodes.get(self.selected_node_id)
        if node and node.node_type == "media" and node.media_path and os.path.exists(node.media_path):
            os.startfile(node.media_path)
        else:
            self.node_status.set("У выбранного узла нет медиа для открытия")

    def _create_link(self, source_id, target_id):
        if source_id == target_id:
            self.node_status.set("Нельзя связать узел сам с собой")
            return
        if source_id not in self.nodes or target_id not in self.nodes:
            self.node_status.set("Один из узлов не существует")
            return
        edge = (source_id, target_id)
        if edge in self.node_edges:
            self.node_status.set("Такая связь уже есть")
            return
        self.node_edges.append(edge)
        self.node_canvas.set_nodes(self.nodes, self.node_edges)
        self.node_status.set(f"Связь создана: {source_id} -> {target_id}")

    def link_nodes(self):
        if self.selected_node_id is None:
            self.node_status.set("Сначала выберите узел")
            return
        try:
            target_id = int(self.node_link_to_var.get().strip())
        except ValueError:
            self.node_status.set("Укажите числовой ID целевого узла")
            return
        self._create_link(self.selected_node_id, target_id)

    def _refresh_network_async(self):
        def worker():
            public_ip = get_public_ip()
            latency = probe_latency()
            self.root.after(0, lambda: self.info_vars["public_ip"].set(public_ip))
            self.root.after(0, lambda: self.info_vars["latency"].set(latency))

        threading.Thread(target=worker, daemon=True).start()


def main():
    root = Tk()
    SchizoOsintApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
