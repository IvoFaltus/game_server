import socket
import sys
import re
import json


IP_PATTERN = r"^((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$"


PORT_PATTERN = r"""^(6553[0-5]|655[0-2]\d|65[0-4]\d{2}|6[0-4]\d{3}|[1-5]?\d{1,4})$"""

def getConfig(atr):
    data= None
    try:
        with open("config.json") as f:
            data = json.load(f)
            return data[atr]
    except Exception as e:
        print(e)
        return data.get("atr") if atr in data.keys() else None       

port,host = None,None

if len(sys.argv) == 1:
    host = getConfig("host")
    port = int(getConfig("port"))

elif len(sys.argv) == 3:
    if not re.fullmatch(IP_PATTERN, sys.argv[1]):
        sys.exit("Invalid IP address")

    if not re.fullmatch(PORT_PATTERN, sys.argv[2]):
        sys.exit("Invalid port")

    host = sys.argv[1]
    port = int(sys.argv[2])

else:
    sys.exit("Usage: python server.py <ip> <port> or no args")


















server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((host, port))
server.listen()
print(f"Listening on {host}:{port}")
while True:
    print("not connceted")
    conn, addr = server.accept()
    print(f"Connected: {addr}")
    conn.sendall(b"succesffully connected\n")
    buffer = b""
    
    while True:
        data = conn.recv(1024)

        if not data:
            print("Client disconnected")
            break
         
        buffer += data

        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)

            line = line.strip(b"\r")

            if not line:
                continue  # ignore empty lines

            print("Received:", line.decode())

            conn.sendall(b"OK\n") # send response every time

    conn.close()



if __name__ == "__main__":
    pass