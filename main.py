from matrixdriver import MatrixDriver
import signal
import sys

driver = None

def graceful_exit(signum, frame):
    print(f"\nReceived signal {signum}, cleaning up before exit...")
    if driver is not None:
        driver.clear_frame()
    print("Exiting gracefully")
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_exit)  
signal.signal(signal.SIGTERM, graceful_exit)

# Main function
if __name__ == "__main__":
    driver = MatrixDriver()
    if not driver.process():
        driver.print_help()
