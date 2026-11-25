from flask import Flask, request
from matrixdriver import MatrixDriver
import api
import signal
import sys
import threading
import requests
import os

matrix_driver_thread = None
driver = None

def graceful_exit(signum, frame):
    print(f"\nReceived signal {signum}, cleaning up before exit...")
    if driver is not None:
        driver.kill()
        # driver.waitForKill()
    if matrix_driver_thread is not None:
        matrix_driver_thread.join()
    print("Exiting gracefully")
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_exit)  
signal.signal(signal.SIGTERM, graceful_exit)

app = Flask(__name__)
app.register_blueprint(api.bp)

# The management page (static/index.html), which uses the API in api.py
@app.route('/', methods=['GET'])
def index():
    return app.send_static_file('index.html')

@app.route('/toggle', methods=['GET'])
def toggle():
    driver.set_brightness(0 if driver.matrix.brightness > 0 else 100)
    return str(driver.matrix.brightness)

# this route is used for setting the brightness of the matrix the brightness value is part of the url
@app.route('/brightness', methods=['POST'])
def brightness():
    value = request.json['value']
    driver.set_brightness(value)
    return str(driver.matrix.brightness)

@app.route('/brightness/increment', methods=['POST'])
def brightness_increment():
    new_brightness = driver.matrix.brightness + 10
    if new_brightness > 100:
        new_brightness = 100
    driver.set_brightness(new_brightness)
    return str(driver.matrix.brightness)

@app.route('/brightness/decrement', methods=['POST'])
def brightness_decrement():
    new_brightness = driver.matrix.brightness - 10
    if new_brightness < 0:
        new_brightness = 0
    driver.set_brightness(new_brightness)
    return str(driver.matrix.brightness)

@app.route('/hello', methods=['GET'])
def hello():
    return str(driver.matrix.brightness)

# Used by deploy/deploy.sh to check the display loop is actually running after a deploy
@app.route('/health', methods=['GET'])
def health():
    if matrix_driver_thread is not None and matrix_driver_thread.is_alive():
        return 'ok'
    return 'matrix driver thread is not running', 503

def run_matrix_driver():
    driver.process()

# Main function
if __name__ == "__main__":
    driver = MatrixDriver()
    app.config['DRIVER'] = driver
    matrix_driver_thread = threading.Thread(target=run_matrix_driver)
    matrix_driver_thread.start()
    api.quiet_polling_logs()
    # PORT is for running it on a computer (see emulator.py); deploy.sh expects 5000 on the Pi
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), use_reloader=False)

