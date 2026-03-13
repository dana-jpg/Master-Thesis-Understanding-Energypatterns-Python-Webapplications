import time
import random

def wait_for_flag(flag_container):
    while not flag_container["ready"]:
        pass

def poll_sensor():
    while True:
        value = random.randint(0, 100)
        if value > 95:
            return value
        time.sleep(0.005)

def build_report(values):
    report = ""
    for v in values:
        report += f"Value: {v}\n" 
    return report
