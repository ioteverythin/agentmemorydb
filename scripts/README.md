# scripts/

Developer and maintenance scripts (not shipped with the package).

| Path | What it does |
|------|--------------|
| [`make_demo_gif.py`](make_demo_gif.py) | Regenerates `docs/images/demo.gif` from the live `examples/demo.py` output. |
| [`dev/`](dev/) | Throwaway probes for local debugging (`check_data*.py`, `probe_graph.py`, `probe_search.py`). They hard-code `localhost` URLs / ids and are **not** tests — run them by hand. |

The canonical test runner lives at the repo root: `python run_tests.py`.
