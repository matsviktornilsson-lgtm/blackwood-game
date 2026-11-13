# Blackwood

Use [the model pipeline](docs/MODEL_PIPELINE.md) for creature assets and [the native migration report](docs/MODEL_PIPELINE_MIGRATION.md) for current infrastructure gaps.

- Use PowerShell 7 and `art/tools/blackwood.ps1` for model work. Begin with `doctor` or `doctor --offline` for read-only inventory. Use the machine-local configuration for Windows paths. Never start, mount or fall back to WSL.
- Treat the user's concept selection, Model Lab approval before rigging and in-game approval before changing the default model as separate decisions. Preserve the approved game behavior and the existing 19-bone rig.
- App starts/stops, GPU/render/generation jobs, installations, and external environment, workflow or workspace changes require explicit approval for the action. Pass approval flags only when that scope has been authorized. Never broaden ComfyUI's custom-node whitelist as a fallback.
- Require the RTX 4090 for model steps with a supported GPU backend. Use PEC for UV segmentation and OptiX or CUDA for Cycles. Stop if a required GPU is unavailable. Report CPU steps explicitly when the installed tool has no GPU variant.
- Keep raw models, weights, generated runs and credentials out of Git. Version new rigged assets under `web/src/assets/werewolf/`. Never overwrite previous model versions or handoffs.
- After every model pipeline run, link its run report in the response. Include the outcome, measured quality, devices, published artifacts, and any failure or remaining approval when applicable. Keep a report for failed and interrupted runs too.
- For local checks use `art/tools/blackwood.ps1 test` and `art/tools/blackwood.ps1 build` with already installed dependencies. Inspect commands and hooks before running other checks.
