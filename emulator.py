"""Stands in for the rgbmatrix library when there's no LED panel, so you can work on the
dashboard and its management page on your computer:

    LED_EMULATOR=1 PORT=5050 python main.py

then open http://localhost:5050. The display's frames show up in the page's preview.
(PORT because macOS uses port 5000 for AirPlay.)
"""


class RGBMatrixOptions:
    def __init__(self):
        self.rows = 32
        self.cols = 32
        self.chain_length = 1
        self.parallel = 1
        self.brightness = 100


class FrameCanvas:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.image = None

    def SetImage(self, image, offset_x=0, offset_y=0, unsafe=True):
        self.image = image.copy()

    def SetPixel(self, x, y, r, g, b):
        pass

    def Clear(self):
        self.image = None


class RGBMatrix:
    def __init__(self, options=None):
        options = options or RGBMatrixOptions()
        self.width = options.cols * options.chain_length
        self.height = options.rows * options.parallel
        self.brightness = options.brightness
        print(f"LED emulator: no LED panel; drawing {self.width}x{self.height} frames for the management page only",
              flush=True)

    def CreateFrameCanvas(self):
        return FrameCanvas(self.width, self.height)

    def SwapOnVSync(self, canvas, framerate_fraction=1):
        return FrameCanvas(self.width, self.height)

    def Clear(self):
        pass
