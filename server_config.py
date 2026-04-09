import argparse
import json
import re
import sys

IP_PATTERN = r"^((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$"
PORT_PATTERN = r"^(6553[0-5]|655[0-2]\d|65[0-4]\d{2}|6[0-4]\d{3}|[1-5]?\d{1,4})$"


def get_config(attr):
    data = None
    try:
        with open("config.json") as f:
            data = json.load(f)
            return data[attr]
    except Exception as e:
        print(e)
        return data.get(attr) if data and attr in data else None


def parse_args():
    parser = argparse.ArgumentParser(description="Socket server")
    parser.add_argument("-H", "--host", help="Server IP address")
    parser.add_argument("-P", "--port", help="Server port")
    parser.add_argument("-passwd", "--password", help="api password", required=True)
    return parser.parse_args()


def load_server_settings():
    args = parse_args()

    host = args.host if args.host else get_config("host")
    port = args.port if args.port else get_config("port")
    password = args.password

    if not host or not port:
        sys.exit("Host and port must be provided via args or config.json")

    if not re.fullmatch(IP_PATTERN, host):
        sys.exit("Invalid IP address")

    if not re.fullmatch(PORT_PATTERN, str(port)):
        sys.exit("Invalid port")

    return host, int(port), password
