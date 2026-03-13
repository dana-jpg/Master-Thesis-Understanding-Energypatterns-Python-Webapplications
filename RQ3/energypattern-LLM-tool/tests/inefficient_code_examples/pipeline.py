import time
import threading
from .utils import wait_for_flag, poll_sensor, build_report
from .math_ops import compute_many_times
from .network import send_with_retry

def process_data(data):
    processed = []
    for item in data:
        print(f"Processing item {item}")
        processed.append(item * 2)
    return processed

def orchestrate_pipeline():
    flag = {"ready": False}

    def delayed_flag_set():
        time.sleep(0.2)
        flag["ready"] = True

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
