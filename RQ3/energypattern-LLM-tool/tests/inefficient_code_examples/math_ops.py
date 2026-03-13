def computation(x):
    return x ** 500000


def compute_many_times():
    results = []
    for _ in range(50):
        results.append(computation(2))
    return results
