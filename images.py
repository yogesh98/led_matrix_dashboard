"""Pictures for the Image component: the built-in icons in icons/, and images uploaded from
the management page.

Uploads are kept as plain files in data/images/ (next to the layout file). Each upload is
shrunk to at most MAX_SIDE pixels on its longest side, since even that is twice the
display, and saved as PNG, or as animated PNG for animations, which keeps every frame and
its timing. An image's id is its folder and file name: "icons/01d" or "uploads/1a2b3c4d-cat".
"""
import io
import os
import re
import secrets
import threading

from PIL import Image, ImageOps

ROOT = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(ROOT, 'icons')
DEFAULT_DIR = os.path.join(ROOT, 'data', 'images')

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000   # refuse anything bigger before decoding it
MAX_SIDE = 128
MAX_FRAMES = 200
MAX_SIZE = 128            # largest box (in LEDs) an image is drawn at

IMAGE_ID = re.compile(r'(icons|uploads)/[A-Za-z0-9_-]{1,80}')

ICON_NAMES = {
    '01': 'Clear', '02': 'Few clouds', '03': 'Clouds', '04': 'Broken clouds', '09': 'Showers',
    '10': 'Rain', '11': 'Thunderstorm', '13': 'Snow', '50': 'Mist',
}


def icon_name(stem):
    if stem == 'wind':
        return 'Wind'
    name = ICON_NAMES.get(stem[:2], stem)
    return f"{name} ({'night' if stem.endswith('n') else 'day'})"


class Asset:
    """An image's frames, plus copies scaled to the sizes it's drawn at"""

    def __init__(self, path, is_icon):
        self.is_icon = is_icon  # icons are white-on-black masks, drawn in the component's color
        with Image.open(path) as im:
            frames, durations = [], []
            for i in range(min(getattr(im, 'n_frames', 1), MAX_FRAMES)):
                im.seek(i)
                if is_icon:
                    mask = im.convert('L')
                    frame = Image.new('RGBA', mask.size, (255, 255, 255, 255))
                    frame.putalpha(mask)
                else:
                    frame = im.convert('RGBA')
                frames.append(frame)
                durations.append(max(20, int(im.info.get('duration') or 100)))
        self.frames = frames
        self.durations = durations
        self.total = sum(durations)
        self.size = frames[0].size
        self._scaled = {}

    def scaled_size(self, width):
        width = max(1, min(MAX_SIZE, width))
        return width, max(1, min(MAX_SIZE, round(width * self.size[1] / self.size[0])))

    def frame(self, width, scaling='auto', at_ms=None):
        """The frame showing at time at_ms (None for the first), scaled to `width` pixels wide.
        scaling: 'sharp' keeps hard pixel edges, 'smooth' blends them (better for photos),
        'auto' is sharp when enlarging and smooth when shrinking."""
        size = self.scaled_size(width)
        if scaling == 'auto':
            scaling = 'sharp' if size[0] >= self.size[0] else 'smooth'
        key = (size, scaling)
        scaled = self._scaled.get(key)
        if scaled is None:
            if len(self._scaled) > 8:  # e.g. after dragging a resize handle through many sizes
                self._scaled.clear()
            method = Image.Resampling.NEAREST if scaling == 'sharp' else Image.Resampling.LANCZOS
            scaled = [f if f.size == size else f.resize(size, method) for f in self.frames]
            self._scaled[key] = scaled
        if at_ms is None or len(scaled) == 1:
            return scaled[0]
        t = int(at_ms) % self.total
        for frame, duration in zip(scaled, self.durations):
            if t < duration:
                return frame
            t -= duration
        return scaled[-1]


def slug(filename):
    stem = os.path.splitext(os.path.basename(filename or ''))[0].lower()
    return re.sub(r'[^a-z0-9]+', '-', stem).strip('-')[:40].strip('-') or 'image'


class ImageLibrary:
    def __init__(self, directory=DEFAULT_DIR):
        self.directory = directory
        self._assets = {}
        self._lock = threading.Lock()

    def path(self, image_id):
        """The file for an image id, or None if the id isn't valid"""
        if not isinstance(image_id, str) or not IMAGE_ID.fullmatch(image_id):
            return None
        folder, name = image_id.split('/', 1)
        return os.path.join(ICON_DIR if folder == 'icons' else self.directory, name + '.png')

    def asset(self, image_id):
        """The image's frames, loaded once and kept until the file changes; None if it's missing"""
        path = self.path(image_id)
        try:
            mtime = os.stat(path).st_mtime if path else None
        except OSError:
            mtime = None
        if mtime is None:
            self._assets.pop(image_id, None)
            return None
        cached = self._assets.get(image_id)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            asset = Asset(path, is_icon=image_id.startswith('icons/'))
        except (OSError, ValueError) as e:
            print(f"Images: couldn't read {path}: {e}", flush=True)
            return None
        with self._lock:
            if len(self._assets) > 64:
                self._assets.clear()
            self._assets[image_id] = (mtime, asset)
        return asset

    def info(self, image_id):
        path = self.path(image_id)
        with Image.open(path) as im:
            width, height = im.size
            frames = getattr(im, 'n_frames', 1)
        folder, name = image_id.split('/', 1)
        builtin = folder == 'icons'
        return {
            'id': image_id,
            'name': icon_name(name) if builtin else name.split('-', 1)[-1].replace('-', ' '),
            'builtin': builtin,
            'width': width,
            'height': height,
            'frames': frames,
        }

    def list(self):
        """Uploads (newest first), then the built-in icons"""
        uploads = []
        if os.path.isdir(self.directory):
            for f in os.listdir(self.directory):
                stem, ext = os.path.splitext(f)
                if ext == '.png' and IMAGE_ID.fullmatch('uploads/' + stem):
                    uploads.append((os.path.getmtime(os.path.join(self.directory, f)), 'uploads/' + stem))
        icons = sorted('icons/' + f[:-4] for f in os.listdir(ICON_DIR) if f.endswith('.png'))
        ids = [image_id for _, image_id in sorted(uploads, reverse=True)] + icons
        result = []
        for image_id in ids:
            try:
                result.append(self.info(image_id))
            except OSError:
                pass  # deleted meanwhile, or not readable
        return result

    def save(self, data, filename):
        """Stores an uploaded image; returns its info. Raises ValueError if it isn't one."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError(f"That file is over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        try:
            im = Image.open(io.BytesIO(data))
            if im.width * im.height > MAX_PIXELS:
                raise ValueError("That image has too many pixels")
            frames, durations = self._frames(im)
        except ValueError:
            raise
        except Exception:
            # Pillow raises all sorts for files it can't read
            raise ValueError("That isn't an image this can read. Try a PNG, JPG, GIF or WebP.") from None

        image_id = f"uploads/{secrets.token_hex(4)}-{slug(filename)}"
        path = self.path(image_id)
        os.makedirs(self.directory, exist_ok=True)
        tmp = path + '.tmp'
        if len(frames) > 1:
            frames[0].save(tmp, format='PNG', save_all=True, append_images=frames[1:], duration=durations, loop=0)
        else:
            frames[0].save(tmp, format='PNG')
        os.replace(tmp, path)
        return self.info(image_id)

    def _frames(self, im):
        count = min(getattr(im, 'n_frames', 1), MAX_FRAMES)
        if count == 1:
            im.draft('RGB', (MAX_SIDE * 2, MAX_SIDE * 2))  # JPEGs decode much faster at a smaller size
            im = ImageOps.exif_transpose(im)               # photos taken sideways
        frames, durations = [], []
        for i in range(count):
            im.seek(i)
            frame = im.convert('RGBA')
            frame.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            frames.append(frame)
            durations.append(max(20, int(im.info.get('duration') or 100)))
        return frames, durations

    def delete(self, image_id):
        """Deletes an upload. Returns False if there's no such upload."""
        if not (isinstance(image_id, str) and image_id.startswith('uploads/')):
            return False
        path = self.path(image_id)
        if not path or not os.path.exists(path):
            return False
        os.remove(path)
        self._assets.pop(image_id, None)
        return True


library = ImageLibrary()
