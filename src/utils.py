import matplotlib.pyplot as plt

def plot_sample_path(telemetry):
    plt.figure(figsize=(6, 6))
    plt.plot(telemetry["X"], telemetry["Y"])
    plt.title("Sample Car Path")
    plt.xlabel("X")
    plt.ylabel("Y")
    plt.axis("equal")
    plt.show()

