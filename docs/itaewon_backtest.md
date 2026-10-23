# Itaewon Crowd-Danger Backtest

**Status:** Simulated reconstruction  
**Purpose:** Explore how exit availability can affect simulated crowd density and danger probability.

## 1. Method

The backtest models a simplified three-zone alley using the project's Monte Carlo crowd simulator. The simulated evening runs from 17:00 to 23:00, with forecasts evaluated in 15-minute windows.

The model uses the project's configured movement, density, arrival, and danger-threshold assumptions. The venue geometry is approximate and is not a surveyed reconstruction of the historical site.

## 2. Scenario assumptions

- Three zones: alley approach, narrow alley, and alley exit.
- Approximate zone area: 162 m² per zone, based on a 45 m × 3.6 m reference dimension.
- Starting counts: 100 people in zone A, 150 in zone B, and 100 in zone C.
- Arrival rate: 20 people per minute into zone A.
- Danger-density threshold: 5 people/m².
- Alert criteria: danger probability of at least 0.30 and predicted time to danger below 15 minutes.
- Two scenarios: final exit open and final exit closed.

These values are scenario inputs, not verified historical crowd measurements.

## 3. Results

| Scenario | First simulated alert |
|---|---|
| Final exit open | No alert during the simulated window |
| Final exit closed | 17:15 |

In the closed-exit scenario, zone C's median predicted density rises above the configured danger threshold. The open-exit scenario does not trigger the alert criteria under the same initial counts and arrival-rate assumptions.

These results demonstrate sensitivity to exit availability within this simplified model. They do not establish what happened historically or prove that an alert would have occurred at a particular time.

## 4. Historical reference markers

The project uses 18:34 as a reference for the first emergency call and approximately 22:15 as a reference for the crush. These are contextual historical markers, not inputs used to force the simulation's alert time.

## 5. Limitations

- This is a simulated reconstruction, not a validated historical prediction.
- The three-zone layout and zone areas are approximate.
- Starting counts and arrival rates are assumed rather than measured.
- The evening is represented as successive 15-minute simulations. Each next window uses the previous forecast's median density to estimate starting counts; this is not a continuous six-hour simulation.
- Excess arrivals are admitted only up to available physical room; the outside queue is not explicitly tracked.
- The closed-exit scenario is a diagnostic comparison, not a claim about the actual historical exit status.
- Results depend on the model assumptions and should not be interpreted as calibrated historical probabilities.

## 6. Reproducibility

Run the backtest from the repository root:

```powershell
python -m imagine.backtest_itaewon
python -m imagine.plot_itaewon_backtest
```

The first command generates `docs/itaewon_backtest.json`. The second generates `docs/itaewon_backtest.png`.

Run the test suite with:

```powershell
python -m pytest -q
```
