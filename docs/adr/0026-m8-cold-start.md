# 0026 — M8 cold start: bytecode in the zips and 512 MB for the apps that load pydantic
- **Status:** Accepted (2026-11-06). Supersedes [0025](0025-m8-deploy-and-crawl.md) decision 12. Refines [0023](0023-m7-demo-estate.md). The rest of 0025 stays in force.

## Context
Step L5 of the M8 runbook ran on 2026-11-06. Three of the five apps returned, and two hit the 10-second timeout:

| Function | Result | Duration | Init | Memory used |
|---|---|---|---|---|
| `support-assistant` | Timed out | 10,000 ms | 74 ms | 101 of 128 MB |
| `contract-insights` | Timed out | 10,000 ms | 65 ms | 96 of 128 MB |
| `shadow-summariser` | Returned | 4,662 ms | 66 ms | 73 of 128 MB |
| `talent-screening` | Returned | 15.8 ms | 69 ms | 33 of 128 MB |
| `invoice-renderer` | Returned | 2.5 ms | 67 ms | 33 of 128 MB |

The logs place the time:
- **Neither timed-out function reached its model.** `mock-bedrock` has no log stream. `mock-openai` ran once, for `shadow-summariser`, after both timeouts. This is why no usage item landed.
- **`shadow-summariser` spent its time before sending anything.** About 4.58 s passed between its `START` and `mock-openai`'s `INIT_START`, and 19 ms passed after the mock finished. Signing and the network are not the cost. Loading boto3 and botocore is.
- **Memory capacity is not the limit.** Lambda shares out CPU in proportion to memory, so 128 MB is about 7% of a vCPU.
- **The zips carried no bytecode.** `/var/task` is read-only, so pydantic and `verity_core` were compiled from source on every cold start.

Timing each function's setup locally, as CPU time and with each dependency's bytecode present or absent, and scaling by `shadow-summariser`'s measured 4.58 s gives these estimates for `support-assistant`. They assume CPU scales with memory and that the runtime's boto3 is already compiled, which is the assumption that fits the timeouts: the other one predicts about 6.5 s at 128 MB, and the function would have returned.

| Memory | As built | With bytecode |
|---|---|---|
| 128 MB | ~16 s | ~9 s |
| 256 MB | ~8 s | ~4.6 s |
| 512 MB | ~4 s | ~2.3 s |

These are estimates, not measurements. L5 and L6 measure the result.

## Decision
1. **Zips that vendor packages carry bytecode for everything they ship.** That is `support-assistant`, `contract-insights`, `verity-crawler` and `verity-probe`. The other five are small, or their cost is in the runtime's boto3, so they stay as they are. The `.py` files stay alongside, for readable tracebacks.
2. **The bytecode is unchecked hash-based.** It holds no timestamp, so the zips' fixed 1980 timestamp cannot invalidate it. Each zip is compiled in a fresh process with a fixed hash seed and a sorted order, because marshal's output depends on the compiling process's state. A build on anything but CPython 3.12 stops, since the runtime would ignore the files.
3. **`support-assistant` and `contract-insights` move to 512 MB, not 256 MB.** The fixture changes with them, so it stays the estate's specification. 256 MB would still miss the 3-second limit, even with bytecode.
4. **`verity-probe` moves to 512 MB as well.** Its setup is close to the apps', so it would probably time out at 128 MB. It is temporary and is not in the fixture.
5. **The 3-second stop applies to `support-assistant` and `contract-insights` only,** as 0025 decision 12 wrote it. The runbook said any cold call. `shadow-summariser` stays at 128 MB: bytecode cannot help it, it returned inside its timeout, and nothing waits on it. Its cold call is recorded in the live results.
6. **Vendored packages' own `tests` folders stay out of every zip.** Bytecode took the crawler zip to 9.4 MiB, over the 8 MB limit in `test_lambda_zips.py`. 2.2 MB of that was networkx's tests, which nothing imports, so they go and the limit stays.
7. **`tests/build` now runs under a plain `pytest`, and so in CI.** `build` is in pytest's default `norecursedirs`, so all 46 zip and handler tests had only ever run when named directly. `norecursedirs` is now pytest's list without `build`, and a test pins that. CI needs PyPI for these tests, not AWS.
8. **If 512 MB with bytecode misses 3 seconds, the next step is 1024 MB.** It is free at these volumes, and the runbook's rule on a bug that defeats two fixes applies.

## Alternatives
| Option | Why not chosen |
|---|---|
| 256 MB alone, as 0025 decided | About 8 s of setup, close to the timeout and far over the limit |
| Bytecode alone at 128 MB | About 9 s of setup, before any model or usage call |
| Move the setup to module load | The same work in the Init phase, which has its own limit. Any extra CPU there is not something we have read in AWS's documentation. Kept as a fallback, since it would change how the apps are written |
| Raise the timeout | Lets a slow cold start pass without making it faster, and breaks the budget test of ADR 0024 |
| Sourceless zips, bytecode only | Smaller, but tracebacks lose their source lines, and nothing needs the space |
| Timestamp-based bytecode | Depends on the file's time matching at load, which the fixed zip timestamp rules out |

## Consequences
- The four zips grow, and the 8 MB limit in `test_lambda_zips.py` still applies.
- CI takes longer, because it now builds the zips twice.
- The zips are no longer independent of the compiling Python: a new 3.12 patch release could change their hashes, which is correct, as the deployed bytes change.
- Live memory now differs between functions. Local and live crawls agree, because the fixture changed too.
- Usage stays far inside the allowance: only the crawler runs on a schedule, and a cold call at 512 MB is a few GB-seconds of 400,000 a month ([0025](0025-m8-deploy-and-crawl.md) has the source).
- **Still unproven until L5 passes:** the arm64 `pydantic_core`, and that the usage client's 0.5 s connect timeout holds on a cold start.
