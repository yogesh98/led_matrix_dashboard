from components.base import Component, Option, rgba
from images import library


class Image(Component):
    type = 'image'
    label = 'Image'
    description = 'A picture, icon or animated GIF'
    options = (
        Option('image', 'Image', 'image', 'icons/01d'),
        Option('width', 'Width', 'number', 16, min=1, max=128, unit='px'),
        Option('scaling', 'Scaling', 'select', 'auto', choices=[
            ('auto', 'Auto'),
            ('sharp', 'Sharp (pixel art)'),
            ('smooth', 'Smooth (photos)'),
        ]),
        Option('color', 'Icon color', 'color', '#ffffff', show_if={'image': 'icons/*'}),
    )
    # The height follows from the width, keeping the picture's proportions
    resize = {'w': 'width'}

    def size(self, opts, ctx):
        asset = library.asset(opts['image'])
        if asset is None:
            return opts['width'], opts['width']
        return asset.scaled_size(opts['width'])

    def draw(self, image, opts, ctx):
        asset = library.asset(opts['image'])
        if asset is None:
            return "This image is missing (it may have been deleted). Pick another one."
        animated = len(asset.frames) > 1
        # The editor shows the first frame; the display plays the animation
        at_ms = None if ctx.preview else ctx.now.timestamp() * 1000
        frame = asset.frame(opts['width'], opts['scaling'], at_ms)
        if asset.is_icon:
            image.paste(rgba(opts['color']), (0, 0), frame.getchannel('A'))
        else:
            image.alpha_composite(frame)
        if animated:
            return f"Animated, {len(asset.frames)} frames. It plays on the display; the editor shows the first frame."
        return None
