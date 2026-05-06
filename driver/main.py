import serial
import time

ser = serial.Serial('COM11', 115200, timeout=1)

while True:

    pkt = bytes([100, 101, 1, 0]) + b'\n'
    ser.write(pkt)

    resp = ser.readline()     # read until newline
    print("sent :", list(pkt))
    print("recv :", list(resp))

    time.sleep(1)