#!/usr/bin/python
import logging
import time
import usb
import math
import signal
import sys
import traceback
import socket
import json
import re
import pprint
import numpy
from os import curdir, sep
from thread import *
from BaseHTTPServer import BaseHTTPRequestHandler
import urlparse

LOGGING_LEVELS = {'critical': logging.CRITICAL,
                  'error': logging.ERROR,
                  'warning': logging.WARNING,
                  'info': logging.INFO,
                  'debug': logging.DEBUG}
connections = list()
timeout = 3
keep_running = True
s = None

class StaticHolder:
    last_json = None

last_json_holder = StaticHolder()

timebase = {
    0 :   (1,"ns"),
    1 :   (2,"ns"),
    2 :   (5,"ns"),
    3 :   (10,"ns"),
    4 :   (20,"ns"),
    5 :   (50,"ns"),
    6 :   (100,"ns"),
    7 :   (200,"ns"),
    8 :   (500,"ns"),
    9 :   (1,"us"),
    0xA : (2,"us"),
    0xB : (5,"us"),
    0xC : (10,"us"),
    0xD : (20,"us"),
    0xE : (50,"us"),
    0xF : (100,"us"),
    0x10: (200,"us"),
    0x11: (500,"us"),
    0x12: (1,"ms"),
    0x13: (2,"ms"),
    0x14: (5,"ms"),
    0x15: (10,"ms"),
    0x16: (20,"ms"),
    0x17: (50,"ms"),
    0x18: (100,"ms"),
    0x19: (200,"ms"),
    0x1A: (500,"ms"),
    0x1B: (1,"s"),
    0x1C: (2,"s"),
    0x1D: (5,"s")
    }
modes_voltage = {
    0 :   (20,"mV"),
    1 :   (50,"mV"),
    2 :   (100,"mV"),
    3 :   (200,"mV"),
    4 :   (500,"mV"),
    5 :   (1,"V"),
    6 :   (2,"V"),
    7 :   (5,"V"),
    8 :   (10,"V"),
    9 :   (20,"V"),
    0xA:  (50,"V"),
    0xB:  (100,"V"),
    0xC:  (200,"V"),
    0xD:  (500,"V")
    }
modes_amperage = {
    0 :   (20,"uA"),
    1 :   (50,"uA"),
    2 :   (100,"uA"),
    3 :   (200,"uA"),
    4 :   (500,"uA"),
    5 :   (1,"mA"),
    6 :   (2,"mA"),
    7 :   (5,"mA"),
    8 :   (10,"mA"),
    9 :   (20,"mA"),
    0xA:  (50,"mA"),
    0xB:  (100,"mA"),
    0xC:  (200,"mA"),
    0xD:  (500,"mA"),
    0xE:  (1,"A"),
    0xF:  (2,"A"),
    0x10: (5,"A")
    }
modes_resistance = {
    0 :  (400, "Ohm"),
    1 :  (4, "KOhm"),
    2 :  (40, "KOhm"),
    3 :  (400, "KOhm"),
    4 :  (4, "MOhm"),
    5 :  (40, "MOhm")
    }


def connect(device_info): # sends command used by MMeter software when pressing the "Connect" button
    logging.debug('Connect DMM')
    device_info.ctrl_transfer(0x21, 0x9, 0, 0, (0x80,0x25,0,0,3))

def disconnect(device_info): # sends command used by MMeter software when pressing the "Disconnect" button
    logging.debug('Disconnect DMM')
    device_info.ctrl_transfer(0x22, 0x9, 0, 0, (0x80,0x25,0,0,3))

def ask(ep): # causes the multimeter to dump a packet of data (up to 401 bytes)
    try:
        logging.debug('Ask for data')
        ep.write((2,0x5a,0,0,0,0,0,0), 0x300)
    except:
        logging.debug('Ask for data error')

def getAnswer(ep): #return list of read bytes; stop reading when timeout or when 10 empty trains appear after some bytes were already read
    result=[]
    t0 = time.time()
    bytesRead = 0
    t = 0
    emptyTrains = 0
    bytesToRead = 361

    # stop condition
    while not (len(result) >= (bytesToRead + 6) or t > timeout or (len(result) > 0 and emptyTrains > 10) ): 
        output = ep.read(8, 100)
        t = time.time() - t0
        actualBytesInOutput = output[0] & 15

        if actualBytesInOutput != 0:
            emptyTrains = 0
            t0 = time.time()
            result.extend(output[1:actualBytesInOutput+1])
            if result[0] == 0x5a: 
                if len(result) >= 8:
                    bytesToRead = result[1]*1000 + result[2]*100 + result[3]*10 + result[4]
            else:
                result = []
        else:
            emptyTrains = emptyTrains + 1
    logging.debug("Bytest to read: %d Bytes: %d (6b header %db data) Empty reads: %d Timeout: %f", bytesToRead, len(result), len(result) - 6, emptyTrains, t)
    return result

def dmmInit():
    d = usb.core.find(idVendor=0x1a86, idProduct=0xe008)

    logging.debug("Found device!")

    # Did we found a device?
    if d is None:
        raise ValueError('Device not found')
    try:
        d.detach_kernel_driver(0)
    except: # this usually mean that kernel driver has already been dettached
        pass

    # Set default configuration and claim the interface
    d.set_configuration()
    cfg = d.get_active_configuration()
    intf = cfg[(0,0)]
    usb.util.claim_interface(d, cfg[(0,0)].bInterfaceNumber)

    # Get IN end point
    ei = usb.util.find_descriptor(
        intf,
        # match the first IN endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_IN)

    # Get OUT end point
    eo = usb.util.find_descriptor(
        intf,
        # match the first OUT endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_OUT)

    assert ei is not None
    assert eo is not None

    return [d, ei, eo, cfg]

def dmmGetData(device):
    global last_good_data
    tries_left = 10
    d = device[0]
    ei = device[1]
    eo = device[2]
    cfg = device[3]
    #clearBuffer(ei)
    ask(eo)
    data = getAnswer(ei)
    while data == [] and tries_left > 0:
        ask(eo)
        data = getAnswer(ei)
        tries_left = tries_left - 1;
    
    logging.debug('Raw data: %s', data)
    if not data or data[0] != 0x5A or len(data) < 41:
        return None
    else:
        return data


def dmmGetRange(data):
    mode=data[6]
    if (mode == 0x00 or mode == 0x80):
        mRange = [modes_voltage[data[11]][0], modes_voltage[data[11]][1], "DC" if data[10] == 0 else "AC"]
    elif (mode == 0x01 or mode == 0x81):
        mRange = [modes_amperage[data[11]][0], modes_amperage[data[11]][1], "DC" if data[10] == 0 else "AC"]
    elif (mode == 0x02 or mode == 0x82):
        mRange = ["-", "Hz", ""]
    elif (mode == 0x03):
        mRange = ["-", "F", ""]
    elif (mode == 0x04):
        mRange = [modes_resistance[data[18]][0], modes_resistance[data[18]][1], ""]
    elif (mode == 0x05):
        mRange = ["-", "OFF", ""]
    elif (mode == 0x06):
        mRange = ["-", "Diode", ""]
    else:
        logging.info('Mode is not unknown')
        return

    return mRange

def cleanFloat(fl):
    return float("{0:.2f}".format(fl))

def cleanFloats(fls):
    return [ cleanFloat(f) for f in fls ]

def dmmDisplayJSON(data, mRange):
    printout=""
    mode=data[6]
    last_char_was_num = False
    last_char = 0
    for i in range(20,50):     #ASCII decoding
        try:
            c_num = data[i]
            c = chr(c_num) if (c_num >= 46 and c_num <= 122) else ' '
            last_char_was_num = (last_char >= 48 and last_char < 58)
            cur_char_is_num = (c_num >= 48 and c_num < 58)
            if last_char_was_num and not cur_char_is_num and c != '.':
              printout += ' ' #ensure a space after numbers
            printout += c
            last_char = c_num;
        except IndexError:  #part of the expected ASCII is missing!
            printout += ' '
    printout = printout.strip()
    logging.debug("PRINTOUT: %s" % (printout))
    pieces = printout.split(' ')
    pieces_found = 0
    float_value_a = 0.0
    float_value_b = 0.0
    try:
        for i in range(0,len(pieces)):
            piece = pieces[i]
            if piece != '' and piece != '0.L' and piece != "M?":
                pieces_found += 1
                if (pieces_found == 1):
                    logging.debug("FLOAT_VALUE_1 = \"%s\"" % (piece))
                    float_value_a = float(piece)
                if (pieces_found == 3 and piece != "."):
                    logging.debug("FLOAT_VALUE_2 = \"%s\"" % (piece))
                    float_value_b = float(piece)
    except ValueError:
        logging.debug("Value Error")                
    smode = 'Unknown'
    scale2 = 'Unknown'
    if (mode == 0x00 or mode == 0x80):
        smode = 'Voltage'
        scale2 = 'Hz'
    elif (mode == 0x01 or mode == 0x81):
        smode = 'Amperage'
    elif (mode == 0x04):
        smode = 'Resistor'
    elif (mode == 0x05):
        smode = 'Off'
    elif (mode == 0x02 or mode == 0x82):
        smode = 'Hz'
    elif (mode == 0x06):
        smode = 'Diode'
    elif (mode == 0x03):
        smode = 'Capacitor'
    plot_data = {"x": [],
                "y": []}
    if len(data) == 361:
        try:
            # Scope screen has 320 i.e. 40pix/div points on x axis
            d13 = data[13]
            logging.debug("d13 = %s" % (d13))
            x = numpy.linspace(0, 8*timebase[d13][0], 320)

            # Scope screen has 128 (-64:64) i.e. 16pix/div points on y axis [x/myInt for x in myList]
            const = float(1)/64*mRange[0]*4
            point = data[12] if data[12]<127 else -(255-data[12])
            offset = float(point)*const
            offsety = [0 for point in data[40:360]]
            iy = [point if point<127 else -(255-point) for point in data[40:360]]
            y = [(float(point)*const) for point in iy]
            plot_data = {
                "x": cleanFloats(x),
                "y": cleanFloats(y)
            }
        except Exception:
            #showException();
            plot_data = {
                "x": [],
                "y": []
            }
    obj = {
        "reading": {
                "scale1": mRange[1],
                "scale2": scale2,
                "display": printout,
                "value1": float_value_a,
                "value2": float_value_b,
            },
        "mode": smode,
        "mode_id": mode,
        "range": mRange[0],
        "plot": plot_data,
        "current": mRange[2],
        "timestamp": int(math.ceil(time.time()*1000))
    }
    broadcastText(json.dumps(obj))

def offData():
    obj = {
        "reading": {
                "scale1": "",
                "scale2": "",
                "value1": 0.0,
                "value2": 0.0
            },
        "plot": { "y": [], "x": [] },
        "mode": "Off",
        "mode_id": 0x05,
        "range": 0,
        "current": "NA",
        "timestamp": int(math.ceil(time.time()*1000))
    }
    return json.dumps(obj)

def dmmDisplayOFF():
    broadcastText(offData())

def exitGracefully(signum, frame):
    # restore the original signal handler
    signal.signal(signal.SIGINT, original_sigint)
    disconnect(device[0])
    s.close
    keep_running = False
    usb.util.release_interface(device[0], device[3][(0,0)].bInterfaceNumber)
    sys.exit(1)

def clientthread(conn):
    while keep_running:
        data = conn.recv(1024)
        if not data:
            break
        #conn.sendall(reply)
    #print "Connection Closed (1/%i)" % (len(connections))
    connections.remove(conn)
    conn.close()

def broadcastText(text):
    last_json_holder.last_json = text
    for conn in connections:
        try:
            conn.sendall("%s\n" % (text))
        except:
            pass

def listenThread():
    HOST = ''   # Symbolic name meaning all available interfaces
    PORT = 8181 # Arbitrary non-privileged port

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    logging.info('Socket created')

    #Bind socket to local host and port
    try:
        s.bind((HOST, PORT))
    except socket.error as msg:
        logging.info('Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
        sys.exit()

    logging.info('Socket bind complete')

    #Start listening on socket
    s.listen(10)
    logging.info('Socket now listening')

    while keep_running:
        #wait to accept a connection - blocking call
        conn, addr = s.accept()
        logging.info('Connected with ' + addr[0] + ':' + str(addr[1]))
        connections.append(conn)
        #start new thread takes 1st argument as a function name to be run, second is the tuple of arguments to the function.
        start_new_thread(clientthread ,(conn,))
    s.close()

class GetHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.do_GET()
    def do_GET(self):
        logging.debug("REQUEST: %s" % (self.path))
        if self.path=="/":
			self.path="/index.html"
        if self.path.startswith('/api.json'):
            try:
                self.send_response(200)
                self.send_header('Content-type','text/javascript')
                self.end_headers()
                if (last_json_holder.last_json != None):
                    self.wfile.write(last_json_holder.last_json)
                else:
                    self.wfile.write(offData())
            except Exception:
                logging.info('web server connection dropped')
            return
        elif (self.path == '/index.html'):
            self.send_response(200)
            self.send_header('Content-type','text/html')
            self.end_headers()
            f = open(curdir + sep + self.path)
            self.wfile.write(f.read())
            f.close()
        elif (self.path == '/index.js'):
            self.send_response(200)
            self.send_header('Content-type','text/javascript')
            self.end_headers()
            f = open(curdir + sep + self.path)
            self.wfile.write(f.read())
            f.close()
    def log_message(self, format, *args):
        return
        
def showException():
    print "********* EXCEPTION *********"
    exc_type, exc_value, exc_traceback = sys.exc_info()
    print exc_type
    print "*** print_tb:"
    traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
    print "*** print_exception:"
    traceback.print_exception(exc_type, exc_value, exc_traceback,
                              limit=2, file=sys.stdout)
    print "*****************************"
    

def webServer():
    from BaseHTTPServer import HTTPServer
    logging.info('Starting HTTP Server')
    server = HTTPServer(('0.0.0.0', 8182), GetHandler)
    
    server.serve_forever()

if __name__ == "__main__":
    # store the original SIGINT handler
    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, exitGracefully)

    # Just to enable easy logging/message printing
    logging_level = logging.CRITICAL
    logging.basicConfig(level=logging_level, stream=sys.stdout,
            format='%(asctime)s %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')

    device = None
    try:
        device = dmmInit()
        time.sleep(4)
        connect(device[0])
    except Exception as ce:
        showException()
        time.sleep(1)
    
    try:
        data = dmmGetData(device)
    except Exception:
        data = None
    
    start_new_thread(listenThread, ())
    start_new_thread(webServer, ())
    while keep_running:
        if (data != None):
            try:
                mRange = dmmGetRange(data)
                dmmDisplayJSON(data, mRange)
            except Exception:
                logging.info("bad fetch")
                showException()
                time.sleep(1)
        else:
            dmmDisplayOFF()
        try:
            data = dmmGetData(device)
        except Exception as gde:
            showException()
            if "disconnected" in str(gde):
                print "Device Disconnected"
                time.sleep(4)
                try:
                    print "Attempting Device Reconnect"
                    device = dmmInit()
                    time.sleep(4)
                    connect(device[0])
                except Exception as ce:
                    showException()
                    time.sleep(1)
    disconnect(device[0])
    usb.util.release_interface(device[0], device[3][(0,0)].bInterfaceNumber)

