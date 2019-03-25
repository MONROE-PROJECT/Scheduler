#!/bin/bash
#
# Author: Mohammad Rajiullah
# Date: March 2019
# License: GNU General Public License v3
# Developed for use by the EU H2020 MONROE and 5GENESIS project
#
# The script automatize monroe node to acces a fipy node using ftp 
# For example, the code uploads a file names send-dat-sensor.py


HOST='192.168.4.1'
USER='micro'
PASSWD='python'

ftp -n -v $HOST << EOT
passive
user $USER $PASSWD
cd flash
ls -la
pu send-dat-sensor.py
bye
EOT
