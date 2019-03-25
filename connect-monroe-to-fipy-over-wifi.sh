#!/bin/bash
#
# Author: Mohammad Rajiullah
# Date: April 2019
# License: GNU General Public License v3
# Developed for use by the EU H2020 MONROE and 5GENESIS project
#
# The script connect a monroe node to wlan in a fipy node 

ifconfig wlan0 up

if [ $? != 0 ]
then
        echo "Wireless card not found!!"
        exit 1
fi

ESSID_=$(iwlist wlan0 s| egrep fipy)
if echo ${ESSID_} |grep -q 'fipy'
then
        ESSID=$(echo ${ESSID_} |cut -d'"' -f 2)
fi
echo ${ESSID}
wpa_passphrase ${ESSID} www.pycom.io > wpa.conf
if [ $? != 0 ]
then
        echo "Wpa_supplecant error!!"
        exit 1
fi
cp wpa.conf /etc/wpa_supplicant.conf
wpa_supplicant -B -iwlan0 -c/etc/wpa_supplicant.conf -Dwext
if [ $? != 0 ]
then
        echo "Wpa_supplecant error!!"
        exit 1
fi
sudo dhclient wlan0
if [ $? != 0 ]
then
        echo "dhclient error!!"
        exit 1
fi
