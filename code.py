# The MIT License (MIT)
#
# Copyright (c) 2023 Mark Komus
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.import board

import digitalio
import time
import biffobear_as3935
import neopixel
import displayio
import terminalio
from adafruit_display_text import label
from adafruit_bitmap_font import bitmap_font
import busio
import adafruit_lc709203f
import alarm

import microcontroller
import os
import wifi
import ssl
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from adafruit_io.adafruit_io import IO_MQTT

import asyncio

#pixel_power = digitalio.DigitalInOut(board.NEOPIXEL_POWER)
#pixel_power.direction = digitalio.Direction.OUTPUT
#pixel_power.value = True

#pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, pixel_order=neopixel.GRBW)
pixel_ring = neopixel.NeoPixel(board.A1, 8, pixel_order=neopixel.GRBW)
pixel_ring.fill(0)
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1)
pixel.fill(0)

i2c = board.I2C()
bat = adafruit_lc709203f.LC709203F(i2c)

#displayio.release_displays()
#i2c = board.I2C()
#i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
#display_bus = displayio.I2CDisplay(i2c, device_address=0x3C)
#display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=128, height=32)
splash = displayio.Group()
font = bitmap_font.load_font("/Helvetica-Bold-16.bdf")

detected_text = label.Label(font, text="Detected: 0", color=0xFFFFFF, x=1, y=10)
splash.append(detected_text)
false_text = label.Label(font, text="False: 0", color=0xFFFFFF, x=110, y=10)
splash.append(false_text)

bat_text = label.Label(font, text="Bat: 0V 0%", color=0xFFFFFF, x=1, y=34)
splash.append(bat_text)

noise_floor_text = label.Label(font, text="NFloor: 0", color=0xFFFFFF, x=130, y=54)
splash.append(noise_floor_text)
noise_int_text = label.Label(font, text="NInt: False", color=0xFFFFFF, x=130, y=74)
splash.append(noise_int_text)

strike_text = label.Label(font, text="", color=0xFFFFFF, x=1, y=100)
splash.append(strike_text)

status_text = label.Label(font, text="Nothing", color=0xFFFFFF, x=1, y=120)
splash.append(status_text)


display = board.DISPLAY.show(splash)
board.DISPLAY.brightness=0.1

#time.sleep(20)

spi = board.SPI()

cs_pin = board.A5
int_pin = board.D5

sensor = biffobear_as3935.AS3935(spi, cs_pin, interrupt_pin=None, baudrate=350_000)

detected = 0
disturbed = 0

sensor.noise_floor_limit = noise_floor_limit = 2
sensor.indoor = False
sensor.watchdog = 2
sensor.spike_threshold = 2
sensor.strike_count_threshold = 1

sensor.tuning_capacitance = 40

CHECK_TIME = 3600
check_in_time = time.monotonic() + CHECK_TIME
upload_time = time.monotonic() + 15

lightning = []

led_off_time = 0

int_alarm = alarm.pin.PinAlarm(int_pin, value=True)

distance = 1000000

TIME_ALARM_TIME = 3600

time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic()+TIME_ALARM_TIME)
while True:
    triggered_alarm = alarm.light_sleep_until_alarms(int_alarm, time_alarm)
    print(f"Alarm set: {triggered_alarm}")
    if triggered_alarm == int_alarm:
        # The interrupt_status is cleared after a read, so assign it
        # to a variable in case you need the value later.
        event_type = sensor.interrupt_status
        if event_type == sensor.LIGHTNING:  # It's a lightning event
            pixel.fill((100,60,0))
            pixel_ring.fill((100,60,0))
            detected += 1
            lightning.append(sensor.energy)
            d = sensor.distance
            print(f"Strike = {sensor.energy} {d} km")
            strike_text.text = f"{sensor.energy} {d}"
            status_text.text = "LIGHTNING"
            if d < distance and d > 0:
                distance = d
            led_off_time = time.monotonic() + 2.0
            time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic()+2)
        elif event_type == sensor.DISTURBER:
            disturbed += 1
            status_text.text = "Disturbed"
            pixel.fill((100,0,0))
            pixel_ring.fill((10,0,0))
            led_off_time = time.monotonic() + 1.0
            time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic()+1)
            print("Disturbed")
        elif event_type == sensor.NOISE:
            print("Noise too high")
            status_text.text = "Noise level high"
            noise_floor_limit += 1
            if noise_floor_limit > 7:
                noise_floor_limit = 7
            sensor.noise_floor_limit = noise_floor_limit
            time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic()+TIME_ALARM_TIME)
        else:
            time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic()+TIME_ALARM_TIME)
    else:
        time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic()+TIME_ALARM_TIME)

    current_time = time.monotonic()

    if current_time > led_off_time:
        pixel.fill((0,0,0))
        pixel_ring.fill((0,0,0))
        led_off_time = 0

    if current_time > check_in_time:
        print(f"Checkin... L:{detected} D:{disturbed} IS:{sensor.interrupt_status}")

        status_text.text = ""
        detected_text.text = f"Bolts: {detected}"
        false_text.text = f"Distrub: {disturbed}"
        noise_floor_text.text = f"NFloor: {sensor.noise_floor_limit}"
        noise_int_text.text = f"NInt: {sensor.interrupt_status}"
        bat_text.text = f"Bat: {bat.cell_voltage}V {bat.cell_percent}%"
        pixel.fill((0,0,10))
        time.sleep(0.05)
        pixel.fill(0)
        check_in_time = time.monotonic()+CHECK_TIME

    if current_time > upload_time:
        print("Uploading to IO...")
        status_text.text = "Uploading"
        if len(lightning) > 0 or (distance > 0 and distance < 100):
            try:
                wifi.radio.enabled = True
                wifi.radio.connect(os.getenv('WIFI_SSID'), os.getenv('WIFI_PASSWORD'))
                # Create a socket pool
                pool = socketpool.SocketPool(wifi.radio)

                # Initialize a new MQTT Client object
                mqtt_client = MQTT.MQTT(
                    broker="io.adafruit.com",
                    username=os.getenv("AIO_USERNAME"),
                    password=os.getenv("AIO_KEY"),
                    socket_pool=pool,
                    ssl_context=ssl.create_default_context(),
                )

                # Initialize Adafruit IO MQTT "helper"
                io = IO_MQTT(mqtt_client)
                io.connect()

                io.publish("thunderbuddy.lightningstrikes", len(lightning))
                lightning = []

                if distance > 0 and distance < 100:
                    io.publish("thunderbuddy.stormdistance", distance)
                distance = 1000000

                time.sleep(1.0)

                io.disconnect()
                wifi.radio.enabled = False
            except Exception as e:
                print("Error: ", str(e))
                time.sleep(1)
                microcontroller.reset()

        print("...Upload done")
        status_text.text = ""

        upload_time = time.monotonic() + 60
