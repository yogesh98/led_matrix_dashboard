"""JSON API for the management page (static/). Everything is under /api."""
import base64
import hashlib
import logging
import os
from urllib.parse import unquote

from flask import Blueprint, current_app, jsonify, request, send_file

import bdf
from components import COMPONENTS
from images import MAX_SIZE, MAX_UPLOAD_BYTES, library as images
from layout import normalize_widget
from prebuilt import prebuilt_screens
from renderer import render_screen, render_widget

bp = Blueprint('api', __name__, url_prefix='/api')


def driver():
    return current_app.config['DRIVER']


def sprite(widget, ctx, known=None):
    """A widget drawn on its own, for the editor to place: its size, its RGBA pixels and
    any note. Pixels are left out if they hash to `known` (the editor already has them)."""
    try:
        image, note = render_widget(widget, ctx)
    except Exception as e:
        return {'error': f"{type(e).__name__}: {e}"}
    data = image.tobytes()
    digest = hashlib.blake2s(data + bytes(image.size), digest_size=8).hexdigest()
    result = {'w': image.width, 'h': image.height, 'hash': digest, 'note': note}
    if known != digest:
        result['rgba'] = base64.b64encode(data).decode('ascii')
    return result


@bp.get('/state')
def state():
    """Everything the page needs to start: the layout, the components and their settings"""
    d = driver()
    ctx = d.context(preview=True)
    components = []
    for component in COMPONENTS.values():
        info = component.catalog()
        info['thumbnail'] = sprite(normalize_widget({'type': component.type, 'id': 'thumbnail'}), ctx)
        components.append(info)
    return jsonify(
        display={'width': d.size[0], 'height': d.size[1]},
        config=d.layout.config,
        components=components,
        fonts=bdf.available_fonts(),
        images=[image_json(info) for info in images.list()],
        prebuilt=[{**screen, 'thumbnail': frame_json(render_screen(screen, ctx))} for screen in prebuilt_screens()],
        brightness=d.matrix.brightness,
    )


def frame_json(frame):
    return {'w': frame.width, 'h': frame.height, 'rgb': base64.b64encode(frame.tobytes()).decode('ascii')}


@bp.get('/prebuilt')
def prebuilt():
    """Each prebuilt screen drawn as it looks right now, for the new-screen picker's live
    previews (with sample weather until the real weather has loaded)"""
    ctx = driver().context(preview=True)
    return jsonify(screens=[{'id': screen['id'], 'frame': frame_json(render_screen(screen, ctx))}
                            for screen in prebuilt_screens()])


@bp.put('/config')
def save_config():
    try:
        config = driver().layout.save(request.get_json())
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(config=config)


@bp.post('/render')
def render():
    """Draws widgets for the editor (with sample data where there's none yet)"""
    body = request.get_json()
    widgets = body.get('widgets') if isinstance(body, dict) else None
    known = body.get('known') if isinstance(body, dict) and isinstance(body.get('known'), dict) else {}
    if not isinstance(widgets, list) or len(widgets) > 1000:
        return jsonify(error="send a list of widgets"), 400
    ctx = driver().context(preview=True)
    sprites = {}
    for raw in widgets:
        try:
            widget = normalize_widget(raw)
        except ValueError as e:
            if isinstance(raw, dict) and isinstance(raw.get('id'), str):
                sprites[raw['id']] = {'error': str(e)}
            continue
        sprites[widget['id']] = sprite(widget, ctx, known.get(widget['id']))
    return jsonify(sprites=sprites)


@bp.get('/live')
def live():
    """What the display is showing right now"""
    d = driver()
    screen, left = d.showing
    frame = d.frame
    return jsonify(
        width=frame.width,
        height=frame.height,
        rgb=base64.b64encode(frame.tobytes()).decode('ascii'),
        screen={'id': screen['id'], 'name': screen['name']} if screen else None,
        remaining=round(left, 1),
        brightness=d.matrix.brightness,
    )


@bp.post('/show')
def show():
    """Puts a screen on the display now, for its duration"""
    body = request.get_json()
    screen_id = body.get('screen_id') if isinstance(body, dict) else None
    if screen_id not in [s['id'] for s in driver().layout.config['screens']]:
        return jsonify(error="no such screen"), 404
    driver().show(screen_id)
    return jsonify(ok=True)


@bp.put('/brightness')
def brightness():
    body = request.get_json()
    try:
        value = max(0, min(100, int(body['value'])))
    except (TypeError, KeyError, ValueError):
        return jsonify(error="send {\"value\": 0-100}"), 400
    driver().set_brightness(value)
    return jsonify(brightness=driver().matrix.brightness)


def image_json(info):
    """An image's info, plus the width that fits it on the display without enlarging it"""
    width, height = driver().size
    scale = min(1, width / info['width'], height / info['height'])
    return {**info, 'fit_width': max(1, min(MAX_SIZE, round(info['width'] * scale)))}


@bp.get('/images')
def list_images():
    return jsonify(images=[image_json(info) for info in images.list()])


@bp.post('/images')
def upload_image():
    """Takes the file as the raw request body, with its name in X-Filename. (Not a form
    upload: a web page on another site can't send this kind of request without CORS allowing it.)"""
    if request.mimetype != 'application/octet-stream':
        return jsonify(error="send the image as application/octet-stream"), 415
    if request.content_length is None:
        return jsonify(error="send a Content-Length"), 411
    if request.content_length > MAX_UPLOAD_BYTES:
        return jsonify(error=f"That file is over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB"), 413
    try:
        info = images.save(request.get_data(cache=False), unquote(request.headers.get('X-Filename', '')))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(image=image_json(info)), 201


@bp.get('/images/file/<path:image_id>')
def image_file(image_id):
    path = images.path(image_id)
    if not path or not os.path.exists(path):
        return jsonify(error="no such image"), 404
    # Ids are never reused, so browsers can keep these
    return send_file(path, mimetype='image/png', max_age=86400)


@bp.delete('/images/<path:image_id>')
def delete_image(image_id):
    if not images.delete(image_id):
        return jsonify(error="no such uploaded image"), 404
    return jsonify(ok=True)


class _QuietPolling(logging.Filter):
    """The page polls /api/live and /api/render several times a second (and /api/prebuilt while
    the new-screen picker is open); keep those out of the log"""

    def filter(self, record):
        message = record.getMessage()
        return not any(path in message for path in ('/api/live', '/api/render', '/api/prebuilt'))


def quiet_polling_logs():
    logging.getLogger('werkzeug').addFilter(_QuietPolling())
