# robotics-radar

**A: keeps a shareable calendar of robotics and Physical AI events near Zürich up to date. B: registers me for the events I accept in it.**

State (2026-10-21): both stages run on the Mac; B registers for real (the last click on Luma is on since 2026-10-21).

```mermaid
flowchart LR
    S["sources<br/>Luma · Voxel51 · ETH/UZH · pages"] --> A["stage A, daily<br/>discover → merge → score"]
    A --> C["shared calendar<br/>public, QR code"]
    A --> T["Todoist<br/>Professional › Robotics"]
    C -- "invitation" --> M["my calendar<br/>I accept or decline"]
    M -- "accepted" --> B["stage B, hourly<br/>Luma form in the radar's Chrome"]
    B --> T
    F["friends, people I meet"] -- "subscribe" --> C
```

| File | What |
|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | what it must do, the decided questions |
| [DESIGN.md](DESIGN.md) | how, the phases of the migration from ChatGPT, the open points |
| [AGENTS.md](AGENTS.md) | rules for agents, the vocabulary |
| [doc/SOURCES.md](doc/SOURCES.md) | where events come from |
| [data/historical-events.json](data/historical-events.json) | ChatGPT's past leads, unverified |
| [config/config.example.yaml](config/config.example.yaml) | the settings' keys; real values in `~/.config/robotics-radar/config.yaml` |

Public repository: no ids, emails, tokens, calendar contents or Todoist exports here.
