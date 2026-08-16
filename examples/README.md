# Examples

Runnable examples for EngramDB.

| Path | What it shows |
|------|---------------|
| [`demo.py`](demo.py) | Zero-setup 60-second tour of the memory lifecycle (short-term → promotion → recall → versioning → context assembly) on the embeddable client. `python examples/demo.py` |
| [`scripts/`](scripts/) | Focused walkthroughs against a running server or the embeddable package (event→memory flow, search, task flow, LangChain/LangGraph, the pip package, and the interactive `agent_demo.py`). |
| [`notebooks/`](notebooks/) | Jupyter notebooks. |

Most `scripts/*.py` talk to a running API at `http://localhost:8100` — start the
stack first (`docker compose up -d`) unless a script says otherwise.
