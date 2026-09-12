#!/usr/bin/env python3
# Minimal telnet client for the Pinball 2000 XINU shell (answers option negotiation, logs in, runs commands).
# usage: python3 macos/telnet-shell.py [cmd ...]   (game launched with --forward-local 2323:23)
import socket,sys,time
IAC,DONT,DO,WONT,WILL=255,254,253,252,251
def session(cmds, host="127.0.0.1", port=2323):
    s=socket.create_connection((host,port),timeout=5); s.settimeout(0.5)
    buf=b""; log=b""
    def pump(t):
        nonlocal buf,log
        end=time.time()+t
        while time.time()<end:
            try: d=s.recv(4096)
            except socket.timeout: continue
            if not d: return False
            buf+=d
            out=bytearray(); i=0
            while i<len(buf):
                if buf[i]==IAC and i+2<len(buf):
                    cmd,opt=buf[i+1],buf[i+2]
                    if cmd in (DO,DONT): s.sendall(bytes([IAC,WONT,opt]))
                    elif cmd in (WILL,WONT): s.sendall(bytes([IAC,DONT,opt]))
                    i+=3
                elif buf[i]==IAC and i+2>=len(buf): break
                else: out.append(buf[i]); i+=1
            buf=buf[i:]; log+=bytes(out)
        return True
    pump(3)
    for c in cmds:
        s.sendall((c+"\r\n").encode()); pump(2.5 if c else 1)
    s.close(); return log.decode('latin1')
cmds = sys.argv[1:] or ["help"]
print(session(["Pin2000","Manager",""] + cmds + ["exit"]))
