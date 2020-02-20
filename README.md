# UNI-T UT81B Digital Multimeter Webserver

This is a python app that creates a small webserver for reading the multimeter data

![Screenshot](https://raw.githubusercontent.com/xitiomet/ut81b-server/master/screenshot.png)

much of the code was borrowed from:
http://www.lowlevel.cz/log/cats/hardware/Python%20software%20for%20scopemeter%20UT81B.html

All i really did was build an html/javascript front end.

This program was designed for python 2.7 and requires the follwing libs

1. libusb
2. pylab
3. numpy

I'm only putting it online so i dont lose it, please dont expect any updates

To use:
```
$ sudo easy_install-2.7 libusb pylab numpy
$ python2.7 ut81b.py
```