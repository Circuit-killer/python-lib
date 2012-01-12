import event
import cares
from socket import AF_UNSPEC
from itertools import compress

def resolve(event_driver, name, family=AF_UNSPEC):
    self = ResolveContext(event_driver)
    timer = event_driver.Timer()
    
    channel = cares.Channel(sock_state_cb=self.sock_state)
    
    channel.gethostbyname(name, family, self.host)
    while self.status is None:
        events = event.Any(watcher for watcher in self.watchers.values())
        
        timeout = channel.timeout()
        if timeout is not None:
            timer.start(timeout)
            events.add(timer)
        
        (trigger, args) = (yield events)
        timer.stop()
        
        if trigger is timer:
            ops = ()
        else:
            (fd, ops) = args
        channel.process_fd(*(fd if (op in ops) else None for op in self.ops))
    cares.check(self.status)
    raise StopIteration(self.hostent)

class ResolveContext:
    def __init__(self, event_driver):
        self.event_driver = event_driver
        self.status = None
        self.watchers = dict()  # File watchers by file descriptor
        self.ops = (self.event_driver.READ, self.event_driver.WRITE)
    
    def sock_state(self, s, *ops):
        if any(ops):
            try:
                watcher = self.watchers[s]
            except LookupError:
                watcher = self.event_driver.FileWatcher(s)
                self.watchers[s] = watcher
            watcher.watch(compress(self.ops, ops))
        else:
            try:
                del self.watchers[s]
            except LookupError:
                pass
    
    def host(self, status, timeouts, hostent):
        self.status = status
        self.hostent = hostent
