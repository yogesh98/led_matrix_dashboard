import RPi.GPIO as GPIO
import time

# Define the GPIO pins for the encoder
#CLK
ENCODER_PIN_A = 5
#DT
ENCODER_PIN_B = 6

# Define the GPIO pin for the switch
#SW
SWITCH_PIN = 12

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(ENCODER_PIN_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(ENCODER_PIN_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(SWITCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Initialize variables
last_encoded = 0
encoder_value = 0

# Define the encoder callback function
def encoder_callback(channel):
    global last_encoded, encoder_value
    MSB = GPIO.input(ENCODER_PIN_A)
    LSB = GPIO.input(ENCODER_PIN_B)
    encoded = (MSB << 1) | LSB
    delta = (encoded - last_encoded) % 4
    if delta == 1:
        encoder_value += 1
    elif delta == 3:
        encoder_value -= 1
    last_encoded = encoded
    switch_state = GPIO.input(SWITCH_PIN)
    print(f"Encoder Value: {encoder_value}, Switch State: {'Pressed' if switch_state == 0 else 'Released'}")

# Add event detection
GPIO.add_event_detect(ENCODER_PIN_A, GPIO.BOTH, callback=encoder_callback)
GPIO.add_event_detect(ENCODER_PIN_B, GPIO.BOTH, callback=encoder_callback)
GPIO.add_event_detect(SWITCH_PIN, GPIO.BOTH, callback=encoder_callback)

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    GPIO.cleanup()
