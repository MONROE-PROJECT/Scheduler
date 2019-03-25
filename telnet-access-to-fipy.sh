#!/bin/bash
#
# Author: Mohammad Rajiullah
# Date: March 2019
# License: GNU General Public License v3
# Developed for use by the EU H2020 MONROE and 5GENESIS project
#
# The script automatize monroe node to acces a fipy node using telnet 
# For example, the code runs a python file names send-dat-sensor.py (WIP)

HOST='192.168.4.1'
USER='micro'
PASSWD='python'
CMD=''

(
echo open "$HOST"
sleep 2
echo "$USER"
sleep 2
echo "$PASSWD"
sleep 2
echo "$CMD"
sleep 2
echo "execfile('send-dat-sensor.py')"
sleep 2
echo "exit"
) | telnet
