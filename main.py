from flask import Flask, request
from matrixdriver import MatrixDriver
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

@app.route('/hello', methods=['GET'])
def hello():
    return str(driver.matrix.brightness)

def run_matrix_driver():
    driver.process()

# Main function
if __name__ == "__main__":
    driver = MatrixDriver()
    matrix_driver_thread = threading.Thread(target=run_matrix_driver)
    matrix_driver_thread.start()
    app.run(host='0.0.0.0', port=5000, use_reloader=False)

