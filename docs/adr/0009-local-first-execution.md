# ADR-0009: Local-first execution for the current phase

- **Status:** Accepted (user decision, 2026-11-18)
- **Date:** 2026-11-18
- **Deciders:** project owner

## Context
The user wants everything to run locally for now. Hardware: Apple M5, 10 cores, 16 GB. Corporate TLS interception (C-3).

## Decision
All perception, compilation and rendering run on the local Mac. External calls only to the Claude API and (optionally) the chosen ASR vendor. Remotion uses its headless shell (installed with `NODE_EXTRA_CA_CERTS`). ffmpeg uses VideoToolbox encode.

## Consequences
- **Good:** no infra cost; fast iteration; media stays local.
- **Bad:** no horizontal scale; 16 GB RAM caps parallel renders (Remotion OffthreadVideo cache defaults to half of RAM).
- **Revisit when:** more than one user, or > ~50 reels/day → move render to a Linux worker / Lambda (cost and licence re-check).
