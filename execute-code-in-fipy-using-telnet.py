"""
Easy telnet client for Pycom.
"""
import telnetlib
import time
import sys


sys.ps1 = ''
sys.ps2 = ''
# timeout value for blocking operations [s]
TO = 5 

# host, 192.168.4.1 by default
host = "192.168.4.1"

# username and password for telnet
username = "micro"
password = "python"

# create telnet object
tel = telnetlib.Telnet(host, port=23, timeout=TO)

# login process
print tel.read_until("Login as: ")
print username
tel.write(username + "\r\n")
print tel.read_until("Password: ", timeout=TO)
print ''
time.sleep(1)
tel.write(password + "\r\n")
time.sleep(.5)
print tel.read_until(">>> ", timeout=TO).strip('>>> ')

# receive command to execute  from the commandline 
# send and execute commands to the pycom device and return the result
indent = '    '
#cmd=sys.argv[1]
cmd="print(\"Hello World!!\")"
print "Sending the following command to the board: ",cmd
tel.write(cmd + '\r\n')
time.sleep(.5)
print (tel.read_until(">>> ", timeout=1).strip('>>> ' + cmd).strip('\r\n'))
