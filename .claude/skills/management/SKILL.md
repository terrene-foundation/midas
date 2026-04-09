# Management Skills

## Artifact Flow

This repo's artifacts are managed by the variant architecture. See `rules/artifact-flow.md`.

### Key Commands

| Command | Context | What it does |
|---------|---------|-------------|
| `/sync` | This repo | Pull and merge latest from upstream USE template |
| `/codify` | This repo | Create artifacts locally + proposal for upstream |

### Flow

```
BUILD repo → /codify → proposal → kailash/ → /sync → USE template → /sync → this repo
```

Artifacts flow through kailash/ (source of truth). Direct BUILD-to-template sync is prohibited.
