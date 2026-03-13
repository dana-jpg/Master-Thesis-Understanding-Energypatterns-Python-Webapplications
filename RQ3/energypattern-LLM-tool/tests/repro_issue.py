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


def computation(x):
    return x ** 500000


def compute_many_times():
    results = []
    for _ in range(50):
        results.append(computation(2))
    return results


def process_data(data):
    processed = []
    for item in data:
        print(f"Processing item {item}")
        processed.append(item * 2)
    return processed


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

def orchestrate_pipeline():
    flag = {"ready": False}

    def delayed_flag_set():
        time.sleep(0.2)
        flag["ready"] = True

    import threading
    threading.Thread(target=delayed_flag_set).start()

    wait_for_flag(flag)

    sensor_values = []
    for _ in range(10):
        sensor_values.append(poll_sensor())

    report = build_report(sensor_values)

    results = compute_many_times()
    processed = process_data(results)

    network_status = send_with_retry()

    return report, processed, network_status


def main():
    report, processed, status = orchestrate_pipeline()
    print("Pipeline finished")
    print("Network status:", status)
    print("Report length:", len(report))
    print("Processed items:", len(processed))


if __name__ == "__main__":
    main()
