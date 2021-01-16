import socket
import ssl
import json
import websocket
from threading import Thread
import random, string

def get_path_value(object, path):
    ro = None
    pointer = object
    if path != None and path != "":
        st = path.split('.')
        for current_value in st:
            if pointer != None:
                if current_value in pointer.keys():
                    ro = pointer[current_value]
                    if isinstance(ro, dict):
                        pointer = ro
                else:
                    ro = None
                    pointer = None
    else:
        ro = object
    return ro

class RouteputChannel():
    def __init__(self, name, connection):
        self.name = name
        self.connection = connection
        self.members = {}
        self.properties = {}
        self.callbacks = {}

    def handle_message(self, msg):
        routeput_meta = msg['__routeput']
        msg_type = None
        src_id = None
        if 'type' in routeput_meta:
            msg_type = routeput_meta['type']
        if 'srcId' in routeput_meta:
            src_id = routeput_meta['srcId']
        if msg_type == 'ConnectionStatus':
            if routeput_meta['connected']:
                member = RouteputRemoteSession(src_id, routeput_meta['properties'], self)
                member.connected = True
                self.members[src_id] = member
                self.trigger('join', member)
            else:
                if src_id in self.members:
                    member = self.members[src_id]
                    member.connected = False
                    del self.members[src_id]
                    self.trigger('leave', member)
        else:
            self.trigger('message', msg)
        if 'setChannelProperty' in routeput_meta.keys():
            for key, value in routeput_meta['setChannelProperty'].items():
                real_value = get_path_value(msg, value)
                self.properties[key] = real_value
                self.trigger('property_change', key, real_value)
        if 'setSessionProperty' in routeput_meta.keys():
            for key, value in routeput_meta['setSessionProperty'].items():
                real_value = get_path_value(msg, value)
                if src_id in self.members:
                    self.members[src_id].properties[key] = real_value
                    self.members[src_id].trigger('property_change', key, real_value)
    
    def trigger(self, event_name, *args, **kwargs):
        if self.callbacks is not None and event_name in self.callbacks:
            if self.connection.debug:
                print("Routeput Firing Channel Callbacks for '%s' %s %s" % (event_name,args, kwargs))
            for callback in self.callbacks[event_name]:
                callback(self, *args, **kwargs)
        else:
            if self.connection.debug:
                print("Routeput NO Channel Callbacks for '%s' %s %s" % (event_name,args, kwargs))

    def on(self, event_name, callback):
        if self.callbacks is None:
            self.callbacks = {}
        if event_name not in self.callbacks:
            self.callbacks[event_name] = [callback]
        else:
            self.callbacks[event_name].append(callback)

    def transmit(self, message):
        if ('__routeput' in message):
            message['__routeput']['channel'] = self.name
        else:
            message['__routeput'] = {'channel': self.name}
        self.connection.transmit(message)

class RouteputRemoteSession():
    def __init__(self, connection_id, properties, channel):
        self.callbacks = {}
        self.connection_id = connection_id
        self.properties = properties
        self.channel = channel
        self.connected = False
    
    def trigger(self, event_name, *args, **kwargs):
        if self.callbacks is not None and event_name in self.callbacks:
            if self.channel.connection.debug:
                print("Routeput Firing Session Callbacks for '%s' %s %s" % (event_name,args, kwargs))
            for callback in self.callbacks[event_name]:
                callback(self, *args, **kwargs)
        else:
            if self.channel.connection.debug:
                print("Routeput NO Session Callbacks for '%s' %s %s" % (event_name,args, kwargs))

    def on(self, event_name, callback):
        if self.callbacks is None:
            self.callbacks = {}
        if event_name not in self.callbacks:
            self.callbacks[event_name] = [callback]
        else:
            self.callbacks[event_name].append(callback)

    def transmit(self, message):
        if ('__routeput' in message):
            message['__routeput']['dstId'] = self.connection_id
        else:
            message['__routeput'] = {'dstId': self.connection_id}
        self.channel.connection.transmit(message)

class RouteputConnection(Thread):
    def getChannel(self, name):
        if name in self.channels:
            return self.channels[name]
        else:
            self.channels[name] = RouteputChannel(name, self)
            return self.channels[name]

    def __init__(self, url, channel_name):
        super(RouteputConnection, self).__init__()
        self.callbacks = {}
        self.properties = {}
        self.channels = {}
        self.connected = False
        self.connection_id = ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase) for _ in range(10))
        self.default_channel = self.getChannel(channel_name)
        self.daemon = True
        self.cancelled = False
        self.debug = False
        self.url = url
        self.ws = websocket.WebSocketApp(self.url,
                    on_message = lambda ws,msg: self.__on_ws_message(ws, msg),
                    on_error   = lambda ws,msg: self.__on_ws_error(ws, msg),
                    on_close   = lambda ws:     self.__on_ws_close(ws),
                    on_open    = lambda ws:     self.__on_ws_open(ws))
        websocket.enableTrace(False)

    def trigger(self, event_name, *args, **kwargs):
        if self.callbacks is not None and event_name in self.callbacks:
            for callback in self.callbacks[event_name]:
                callback(self, *args, **kwargs)

    def on(self, event_name, callback):
        if self.callbacks is None:
            self.callbacks = {}
        if event_name not in self.callbacks:
            self.callbacks[event_name] = [callback]
        else:
            self.callbacks[event_name].append(callback)

    def run(self):
        while self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}):
            pass

    def __on_ws_message(self, ws, message):
        if self.debug:
            print("Routeput Receive: %s" % (message))
        msg = json.loads(message)
        routeput_meta = msg['__routeput']
        msg_type = None
        if 'type' in routeput_meta:
            msg_type = routeput_meta['type']
        channel = None
        if 'channel' in routeput_meta:
            channel = self.getChannel(routeput_meta['channel'])

        if (msg_type == 'connectionId'):
            self.connection_id = routeput_meta['connectionId']
            self.properties = routeput_meta['properties']
            self.default_channel = self.getChannel(routeput_meta['channel'])
            self.default_channel.properties = routeput_meta['channelProperties']
        elif (msg_type == 'ping'):
            self.transmit({'__routeput': {'type': 'pong', 'pingTimestamp': routeput_meta['timestamp']}})
        elif (msg_type == 'ConnectionStatus'):
            if channel:
                channel.handle_message(msg)
        else:
            self.trigger("message", msg)
            if channel:
                channel.handle_message(msg)

    def __on_ws_error(self, ws, error):
        self.connected = False
        if self.debug:
            print(error)

    def __on_ws_close(self, ws):
        self.connected = False
        if self.debug:
            print("### closed ###")

    def __on_ws_open(self, ws):
        self.connected = True
        mm = {"__routeput": {
                                "type": "connectionId",
                                "channel": self.default_channel.name,
                                "properties": self.properties,
                                "connectionId": self.connection_id
                            }
             }
        self.transmit(mm)
        if self.debug:
            print("### opened ###")

    def transmit(self, message):
        if self.connected and isinstance(message, dict):
            if ('__routeput' in message):
                routeput_meta = message['__routeput']
                if not 'srcId' in routeput_meta:
                    routeput_meta['srcId'] = self.connection_id
            else:
                message['__routeput'] = {'srcId': self.connection_id}
            out_string = json.dumps(message)
            if self.debug:
                print("Routeput Transmit: %s" % (out_string))
            self.ws.send("%s" % (out_string))