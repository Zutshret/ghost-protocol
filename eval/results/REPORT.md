# GHOST PROTOCOL: evaluation report

100 simulated incidents per cell (seeds 0 to 99), scripted human who approves the correct fix when it is offered, no LLM. Numbers are means with 95% confidence intervals in brackets. Likelihood tables were learned on different seeds (1000-1199).

## 1. Modes compared, per scenario

Recovery time = ticks from fault start until healthy (30 = never recovered). Wrong actions = actions that do not fix the true cause. Unsafe = failover that risked data consistency (the engine's validator checks the true replication lag in every mode, so this stays 0%; the standalone runbook in run_scenarios.py, which trusts noisy dashboards, reaches about 34% on S5). Brier for Mode C is computed on the team's averaged belief, which is for display, not for deciding.

### S1: clear DB fault

| Mode | Right first time | Recovery (ticks) | Availability | Wrong actions | Asked a human | Unsafe | Brier (lower=better) |
|---|---|---|---|---|---|---|---|
| A Runbook | 100% (96% to 100%) | 6.3 (6.1 to 6.4) | 98% (98% to 98%) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) | 0% (0% to 4%) | n/a (no probabilities) |
| B Agents + aggregator | 100% (96% to 100%) | 6.0 (6.0 to 6.1) | 98% (98% to 98%) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) | 0% (0% to 4%) | 0.000 (-0.000 to 0.000) |
| C Peer negotiation | 100% (96% to 100%) | 6.0 (6.0 to 6.1) | 98% (98% to 98%) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) | 0% (0% to 4%) | 0.037 (0.035 to 0.040) |
| D Hybrid | 100% (96% to 100%) | 6.0 (6.0 to 6.1) | 98% (98% to 98%) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) | 0% (0% to 4%) | 0.007 (0.004 to 0.011) |

### S2: deploy that looks like an attack

| Mode | Right first time | Recovery (ticks) | Availability | Wrong actions | Asked a human | Unsafe | Brier (lower=better) |
|---|---|---|---|---|---|---|---|
| A Runbook | 75% (66% to 82%) | 8.0 (7.7 to 8.4) | 97% (96% to 97%) | 0.25 (0.18 to 0.34) | 0% (0% to 4%) | 0% (0% to 4%) | n/a (no probabilities) |
| B Agents + aggregator | 100% (96% to 100%) | 7.0 (7.0 to 7.0) | 98% (98% to 98%) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) | 0% (0% to 4%) | 0.000 (-0.000 to 0.000) |
| C Peer negotiation | 100% (96% to 100%) | 7.0 (7.0 to 7.0) | 98% (98% to 98%) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) | 0% (0% to 4%) | 0.199 (0.193 to 0.205) |
| D Hybrid | 97% (92% to 99%) | 7.1 (7.0 to 7.3) | 98% (98% to 98%) | 0.03 (0.01 to 0.08) | 0% (0% to 4%) | 0% (0% to 4%) | 0.105 (0.038 to 0.173) |

### S3: dependency timeout

| Mode | Right first time | Recovery (ticks) | Availability | Wrong actions | Asked a human | Unsafe | Brier (lower=better) |
|---|---|---|---|---|---|---|---|
| A Runbook | 98% (93% to 99%) | 8.2 (8.0 to 8.3) | 98% (98% to 98%) | 0.02 (0.01 to 0.07) | 0% (0% to 4%) | 0% (0% to 4%) | n/a (no probabilities) |
| B Agents + aggregator | 100% (96% to 100%) | 8.0 (8.0 to 8.0) | 98% (98% to 98%) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) | 0% (0% to 4%) | 0.000 (-0.000 to 0.000) |
| C Peer negotiation | 100% (96% to 100%) | 9.2 (9.0 to 9.4) | 98% (98% to 98%) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) | 0% (0% to 4%) | 0.176 (0.164 to 0.187) |
| D Hybrid | 100% (96% to 100%) | 8.1 (8.0 to 8.2) | 98% (98% to 98%) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) | 0% (0% to 4%) | 0.016 (0.005 to 0.026) |

### S5: ambiguous, high stakes

| Mode | Right first time | Recovery (ticks) | Availability | Wrong actions | Asked a human | Unsafe | Brier (lower=better) |
|---|---|---|---|---|---|---|---|
| A Runbook | 0% (0% to 4%) | 30.0 (30.0 to 30.0) | 87% (87% to 87%) | 2.01 (1.99 to 2.03) | 0% (0% to 4%) | 0% (0% to 4%) | n/a (no probabilities) |
| B Agents + aggregator | 97% (92% to 99%) | 9.1 (9.0 to 9.3) | 97% (97% to 97%) | 0.03 (0.01 to 0.08) | 100% (96% to 100%) | 0% (0% to 4%) | 0.061 (0.003 to 0.119) |
| C Peer negotiation | 98% (93% to 99%) | 6.2 (6.1 to 6.4) | 98% (98% to 98%) | 0.02 (0.01 to 0.07) | 100% (96% to 100%) | 0% (0% to 4%) | 0.125 (0.076 to 0.174) |
| D Hybrid | 94% (88% to 97%) | 8.2 (8.0 to 8.3) | 97% (97% to 98%) | 0.06 (0.03 to 0.12) | 100% (96% to 100%) | 0% (0% to 4%) | 0.339 (0.256 to 0.423) |

## 2. Paired difference versus the runbook (same seeds)

Positive 'right first time' and availability are good; negative recovery time is good.

| Scenario | Mode minus runbook | Right first time | Recovery (ticks) | Availability |
|---|---|---|---|---|
| S1 | B Agents + aggregator | +0 pts (+0 to +4) | -0.3 (-0.4 to -0.1) | +0 pts (+0 to +0) |
| S1 | C Peer negotiation | +0 pts (+0 to +4) | -0.2 (-0.4 to -0.1) | +0 pts (+0 to +0) |
| S1 | D Hybrid | +0 pts (+0 to +4) | -0.3 (-0.4 to -0.1) | +0 pts (+0 to +0) |
| S2 | B Agents + aggregator | +25 pts (+18 to +34) | -1.0 (-1.4 to -0.7) | +1 pts (+1 to +2) |
| S2 | C Peer negotiation | +25 pts (+18 to +34) | -1.0 (-1.4 to -0.7) | +1 pts (+1 to +2) |
| S2 | D Hybrid | +22 pts (+15 to +31) | -0.9 (-1.2 to -0.6) | +1 pts (+1 to +2) |
| S3 | B Agents + aggregator | +2 pts (+1 to +7) | -0.1 (-0.3 to -0.0) | +0 pts (-0 to +0) |
| S3 | C Peer negotiation | +2 pts (+1 to +7) | +1.0 (+0.8 to +1.2) | -0 pts (-0 to -0) |
| S3 | D Hybrid | +2 pts (+1 to +7) | -0.0 (-0.1 to +0.1) | +0 pts (-0 to +0) |
| S5 | B Agents + aggregator | +97 pts (+92 to +99) | -20.9 (-21.0 to -20.7) | +11 pts (+10 to +11) |
| S5 | C Peer negotiation | +98 pts (+93 to +99) | -23.8 (-23.9 to -23.6) | +11 pts (+11 to +12) |
| S5 | D Hybrid | +94 pts (+88 to +97) | -21.9 (-22.0 to -21.7) | +11 pts (+11 to +11) |

## 3. Ablation: remove one agent's evidence

Right first time and 'asked a human' for each mode, with the named agent blind. A big drop means that agent carries information the others cannot replace.


### Mode B: Agents + aggregator

| Team | S1: right / asked human | S2: right / asked human | S3: right / asked human | S5: right / asked human |
|---|---|---|---|---|
| (full team) | 100% / 0% | 100% / 0% | 100% / 0% | 97% / 100% |
| without gateway | 100% / 0% | 100% / 0% | 100% / 0% | 100% / 100% |
| without payments | 100% / 0% | 100% / 0% | 100% / 0% | 95% / 100% |
| without database | 99% / 0% | 100% / 0% | 100% / 0% | 0% / 100% |
| without security | 100% / 0% | 100% / 0% | 100% / 0% | 100% / 100% |
| without deployment | 99% / 0% | 100% / 0% | 100% / 0% | 98% / 100% |

### Mode C: Peer negotiation

| Team | S1: right / asked human | S2: right / asked human | S3: right / asked human | S5: right / asked human |
|---|---|---|---|---|
| (full team) | 100% / 0% | 100% / 0% | 100% / 0% | 98% / 100% |
| without gateway | 100% / 0% | 100% / 0% | 100% / 0% | 97% / 100% |
| without payments | 100% / 0% | 100% / 0% | 100% / 0% | 99% / 100% |
| without database | 100% / 1% | 100% / 0% | 100% / 0% | 8% / 100% |
| without security | 100% / 0% | 100% / 0% | 100% / 0% | 100% / 100% |
| without deployment | 100% / 4% | 100% / 0% | 100% / 0% | 98% / 100% |

## 4. Decision rule variants (Mode B)

Same engine, different rule for act / probe / ask a human.

| Rule | Scenario | Right first time | Recovery (ticks) | Availability | Asked a human | Unsafe |
|---|---|---|---|---|---|---|
| expected-cost (default) | S1 | 100% (96% to 100%) | 6.0 (6.0 to 6.1) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| expected-cost (default) | S2 | 100% (96% to 100%) | 7.0 (7.0 to 7.0) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| expected-cost (default) | S3 | 100% (96% to 100%) | 8.0 (8.0 to 8.0) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| expected-cost (default) | S5 | 97% (92% to 99%) | 9.1 (9.0 to 9.3) | 97% (97% to 97%) | 100% (96% to 100%) | 0% (0% to 4%) |
| fixed thresholds (75% / 90%) | S1 | 100% (96% to 100%) | 6.0 (6.0 to 6.1) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| fixed thresholds (75% / 90%) | S2 | 100% (96% to 100%) | 7.0 (7.0 to 7.0) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| fixed thresholds (75% / 90%) | S3 | 100% (96% to 100%) | 8.0 (8.0 to 8.0) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| fixed thresholds (75% / 90%) | S5 | 98% (93% to 99%) | 9.1 (9.0 to 9.2) | 97% (97% to 97%) | 100% (96% to 100%) | 0% (0% to 4%) |
| expected-cost, human is cheap (1) | S1 | 100% (96% to 100%) | 6.0 (6.0 to 6.0) | 98% (98% to 98%) | 1% (0% to 5%) | 0% (0% to 4%) |
| expected-cost, human is cheap (1) | S2 | 100% (96% to 100%) | 7.0 (7.0 to 7.0) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| expected-cost, human is cheap (1) | S3 | 100% (96% to 100%) | 8.0 (8.0 to 8.0) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| expected-cost, human is cheap (1) | S5 | 98% (93% to 99%) | 6.1 (6.0 to 6.2) | 98% (98% to 98%) | 100% (96% to 100%) | 0% (0% to 4%) |
| expected-cost, human is costly (8) | S1 | 100% (96% to 100%) | 6.0 (6.0 to 6.1) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| expected-cost, human is costly (8) | S2 | 100% (96% to 100%) | 7.0 (7.0 to 7.0) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| expected-cost, human is costly (8) | S3 | 100% (96% to 100%) | 8.0 (8.0 to 8.0) | 98% (98% to 98%) | 0% (0% to 4%) | 0% (0% to 4%) |
| expected-cost, human is costly (8) | S5 | 98% (93% to 99%) | 9.1 (9.0 to 9.2) | 97% (97% to 97%) | 100% (96% to 100%) | 0% (0% to 4%) |

## 5. Is the belief engine honest about its confidence?

All agents' clues pooled, ticks 7-12, 60 seeds (2000+). Average confidence should be close to accuracy.

| Scenario | Accuracy | Average confidence | Brier | Uncertainty (bits) |
|---|---|---|---|---|
| S1 | 100% | 100% | 0.000 | 0.00 |
| S2 | 100% | 100% | 0.000 | 0.00 |
| S3 | 100% | 100% | 0.003 | 0.01 |
| S5 | 80% | 84% | 0.270 | 0.56 |

## 6. Mode D: what the router does when two runbook rules match

The runbook's rules can match at the same time (S2: 'traffic spike' and 'recent deploy'). The default hands the decision to the agents at that point. The naive variant applies the first matching rule, which reproduces the runbook's misfire. The default was chosen after seeing this result, so both are shown.

| Mode D variant | Scenario | Right first time | Recovery (ticks) | Wrong actions | Asked a human |
|---|---|---|---|---|---|
| conflict hand-off (default) | S1 | 100% (96% to 100%) | 6.0 (6.0 to 6.1) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) |
| conflict hand-off (default) | S2 | 97% (92% to 99%) | 7.1 (7.0 to 7.3) | 0.03 (0.01 to 0.08) | 0% (0% to 4%) |
| conflict hand-off (default) | S3 | 100% (96% to 100%) | 8.1 (8.0 to 8.2) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) |
| conflict hand-off (default) | S5 | 94% (88% to 97%) | 8.2 (8.0 to 8.3) | 0.06 (0.03 to 0.12) | 100% (96% to 100%) |
| naive: first matching rule wins | S1 | 100% (96% to 100%) | 6.0 (6.0 to 6.1) | 0.00 (0.00 to 0.04) | 0% (0% to 4%) |
| naive: first matching rule wins | S2 | 75% (66% to 82%) | 8.0 (7.7 to 8.3) | 0.25 (0.18 to 0.34) | 0% (0% to 4%) |
| naive: first matching rule wins | S3 | 98% (93% to 99%) | 8.2 (8.0 to 8.3) | 0.02 (0.01 to 0.07) | 0% (0% to 4%) |
| naive: first matching rule wins | S5 | 94% (88% to 97%) | 8.2 (8.0 to 8.4) | 0.06 (0.03 to 0.12) | 100% (96% to 100%) |
