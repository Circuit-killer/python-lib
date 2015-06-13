from __future__ import print_function

import cares
from socket import (AF_UNSPEC, AF_INET, AF_INET6)
from sys import stderr
from asyncio import Future

def name_connect(event_driver, address, Socket, callback=None, message=None):
    hostname = address[0]
    if message is not None:
        callback = MessageCallback(message)
    
    resolved = False
    
    for family in (AF_UNSPEC, AF_INET6, AF_INET):
        if callback is not None:
            callback.lookingup(hostname, family)
        try:
            hostent = (yield resolve(event_driver, hostname, family))
        except EnvironmentError as e:
            print(e, file=stderr)
            continue
        resolved = True
        
        sock = Socket(hostent.addrtype)
        try:
            for attempt in hostent.addr_list:
                attempt = (attempt,) + address[1:]
                if callback is not None:
                    callback.connecting(attempt)
                try:
                    yield sock.connect(attempt)
                except EnvironmentError as e:
                    print(e, file=stderr)
                    continue
                break
            else:
                sock.close()
                continue
        except:
            sock.close()
            raise
        raise StopIteration(sock)
    
    else:
        if resolved:
            raise EnvironmentError("All addresses unconnectable: {0}".format(
                hostname))
        else:
            raise EnvironmentError("Failure resolving {0}".format(hostname))

class MessageCallback(object):
    def __init__(self, callback):
        self.callback = callback
    def lookingup(self, name, family):
        self.callback("Looking up {0} (family {1})".format(name, family))
    def connecting(self, address):
        self.callback("Connecting to {0}:{1}".format(*address))

def resolve(event_driver, name, family=AF_UNSPEC):
    self = ResolveContext(loop=event_driver)
    channel = cares.Channel(sock_state_cb=self.sock_state)
    channel.gethostbyname(name, family, self.host)
    while self.status is None:
        timeout = channel.timeout()
        if timeout is not None:
            timeout_result = (None, None)
            timeout = event_driver.call_later(timeout,
                self.sock_future.set_result, timeout_result)
        result = yield from self.sock_future
        if timeout is not None and result is not timeout_result:
            timeout.cancel()
        self.sock_future = Future(loop=event_driver)
        [read, write] = result
        if read is not None:
            self.loop.add_reader(read, self.sock_future.set_result, result)
        if write is not None:
            self.loop.add_writer(write, self.sock_future.set_result, result)
        channel.process_fd(read, write)
    cares.check(self.status)
    raise StopIteration(self.hostent)

class ResolveContext:
    def __init__(self, *, loop):
        self.loop = loop
        self.sock_future = Future(loop=self.loop)
        self.status = None
        self.reading = set()
        self.writing = set()
    
    def sock_state(self, s, read, write):
        if read:
            if s not in self.reading:
                result = (s, None)
                self.loop.add_reader(s, self.sock_future.set_result, result)
                self.reading.add(s)
        else:
            if s in self.reading:
                self.loop.remove_reader(s)
                self.reading.remove(s)
        
        if write:
            if s not in self.writing:
                result = (None, s)
                self.loop.add_writer(s, self.sock_future.set_result, result)
                self.writing.add(s)
        else:
            if s in self.writing:
                self.loop.remove_writer(s)
                self.writing.remove(s)
    
    def host(self, status, timeouts, hostent):
        self.status = status
        self.hostent = hostent
