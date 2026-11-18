# Hinglish ASR bake-off

2 clip(s): money, order · timing reference on 0 clip(s)

| engine | composite | WER | CER | fillers kept | onset err ms | ≤100 ms | bad timing | RTF | Devanagari |
|---|---|---|---|---|---|---|---|---|---|
| oriserve-apex | 0.965 | 0.056 | 0.015 | – | – | – | 0.000 | 4.631 | 0.000 |
| shruti | 0.941 | 0.080 | 0.037 | – | – | – | 0.000 | 0.082 | 0.814 |
| whisper-turbo | 0.881 | 0.167 | 0.072 | – | – | – | 0.000 | 1.714 | 0.894 |
| indicconformer | 0.799 | 0.297 | 0.104 | – | – | – | 0.000 | 0.939 | 1.000 |
| whisper-large-v3 | 0.778 | 0.272 | 0.171 | – | – | – | 0.000 | 3.428 | 1.000 |

**Winner (composite = {'accuracy': 0.6, 'fillers': 0.2, 'sync': 0.2}, scaled down by bad timing): oriserve-apex**

Scores use script-agnostic keys (`reel.script.key`): Devanagari is romanised and spelling variants folded before comparison. Hypotheses per engine are in `<engine>/<clip>.txt` — read a few before trusting the numbers.
