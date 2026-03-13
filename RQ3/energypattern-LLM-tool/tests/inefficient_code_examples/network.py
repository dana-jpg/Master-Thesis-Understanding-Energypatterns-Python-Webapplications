import random

class ConnectionError(Exception):
    pass

def network_call():
    if random.random() < 0.9:
        raise ConnectionError("Network failed")
    return "OK"


def send_with_retry():
    while True:
        try:
            return network_call()
        except ConnectionError:
            continue
