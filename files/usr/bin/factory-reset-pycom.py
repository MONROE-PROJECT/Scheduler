#!/usr/bin/env python
#
# Author: Jonas Karlsson
# Date: April 2016
# License: GNU General Public License v3
# Developed for use by the EU H2020 MONROE project

"""
This code erases the flash and reboots the device, ie a clean slate start

Example usage:
    ./factory-reset-pycom.py --device /dev/ttyUSB2

Or:

    python ./factory-reset-pycom.py /dev/ttyUSB2

"""
from __future__ import print_function
import argparse
import pyboard

cmd_parser = argparse.ArgumentParser(description='Factory resets the pycom board.')
cmd_parser.add_argument('--device', default='/dev/ttyUSB2', help='the serial device of the pyboard')
cmd_parser.add_argument('--baudrate', default=115200, help='the baud rate of the serial device')
cmd_parser.add_argument('--wait', default=0, type=int, help='seconds to wait for USB connected board to become available')
args = cmd_parser.parse_args()

pyb = pyboard.Pyboard(device=args.device, baudrate=args.baudrate, wait=args.wait)
print("Connected to board {}, executing reset... ".format(args.device), end='')
pyb.enter_raw_repl()
pyb.exec_raw_no_follow("import os,machine; os.mkfs('/flash'); machine.reset()")
pyb.exit_raw_repl()
pyb.close()
print("Done")
