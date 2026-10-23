
"""Plot the Itaewon simulated reconstruction results."""
import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "docs" / "itaewon_backtest.json"
OUTPUT_PATH = ROOT / "docs" / "itaewon_backtest.png"


def main() -> None:
    with INPUT_PATH.open("r", encoding="utf-8") as file:
        result = json.load(file)

    scenarios = result["scenarios"]
    fig, ax = plt.subplots(figsize=(10, 5.5))

    for scenario in scenarios:
        timeline = scenario["timeline"]
        times = [item["time"] for item in timeline]
        risks = [item["p_danger"] for item in timeline]
        label = "Exit closed" if scenario["exit_closed"] else "Exit open"
        ax.plot(times, risks, marker="o", markersize=3, label=label)

    ax.axhline(
        y=0.30,
        linestyle="--",
        label="Alert threshold (p_danger = 0.30)",
    )
    ax.set_title("Itaewon Simulated Reconstruction — Crowd Danger Probability")
    ax.set_xlabel("Simulated time")
    ax.set_ylabel("Probability of reaching danger density")
    ax.set_ylim(0, 1.05)
    ax.tick_params(axis="x", rotation=45)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.text(
        0.01,
        0.01,
        "Simplified simulation, not a validated historical prediction.",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(OUTPUT_PATH, dpi=180, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved chart to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
