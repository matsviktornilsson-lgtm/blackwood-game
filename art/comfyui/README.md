# Blackwoods ComfyUI-workflows

Här finns Blackwoods fem presets. Varje preset har en GUI-graf (`.json`) och en API-graf (`.api.json`) med samma noder och länkar. API-graferna är källan för CLI:n.

| Preset | Utdata |
|---|---|
| `blackwood_werewolf_concept` | Standard. FLUX.1 dev med FP8, XLabs Realism-LoRA, 28 steg och åtta 1024×1536-bilder. |
| `blackwood_werewolf_concept_schnell` | Alternativet `concept-schnell` med fyra steg och åtta 1024×1536-bilder. |
| `blackwood_werewolf_concept_photo` | `concept --preset concept-photo` med samma FLUX.1 dev-graf som `concept` och en fast fotografisk prompt utan `--body`. |
| `blackwood_werewolf_to_3d` | En texturerad TRELLIS.2 512³ RAW-GLB och en frilagd BiRefNet-PNG per vald bild. |
| `blackwood_werewolf_to_3d_1024_lowvram` | En texturerad RAW-GLB från en 512 → 1024-kaskad och en frilagd PNG. Samma kvantiserade modell och en mindre atlas. Minnesprofilen behöver mätas. |

Standardpresetet följer batch5:s Flux-inställningar och använder den uppdaterade varulvsprompten. TRELLIS-graferna använder ComfyUI:s inbyggda noder med GPU-baserad PEC-segmentering för UV-atlasen. UV-uppackning och PBR-bakning skapar en texturerad RAW. Förenklingen sker i GAME. [ComfyUI:s TRELLIS.2-guide](https://github.com/Comfy-Org/docs/blob/main/tutorials/3d/trellis2.mdx)

`bindings.json` har nycklarna `concept`, `concept-photo`, `concept-schnell`, `3d` och `3d-1024`. Varje post anger:

- `workflow_sha256` för de exakta API-exportbytes som granskats.
- `preset` med tripplar `[nod-ID, inputnamn, värde]` för skyddade produktionsvärden, inklusive konceptets batchstorlek respektive 512³-läget.
- `prefix` med `[nod-ID, inputnamn]` för ComfyUI:s relativa output-prefix och `output` med `[nod-ID, fält]` för den sparande nodens historikreferenser. Referenserna behöver innehålla `filename`, `subfolder` och `type: "output"` som kan hämtas via `/view`.
- För koncept, `seed` och `body` med `[nod-ID, inputnamn]` och `body_token` med den exakta kroppsbeskrivningen att ersätta en gång i den granskade texten.
- För 3D, `image` med `[nod-ID, inputnamn]` för vald PNG och vid behov `requires_worker: true` när grafens native-noder behöver den separata TRELLIS-miljön. Worker-anslutningen hör till den granskade serverinstallationen.
- För 3D, `cutout.prefix` och `cutout.output` för den frilagda PNG som projektionen hämtar från samma körning.

`blackwood.ps1 doctor` kontrollerar bindningarnas hash och jämför grafens noder och modellval med `/object_info`. Det är en statisk kontroll. Efter separat distributionsgodkännande kan `blackwood.ps1 stage-workflows --destination '<godkänd Windows-mapp>' --approved` kopiera de konfigurerade källorna byte för byte. Lägg till GUI-filerna i `workflow_gui` om de ska distribueras. En fil med samma namn och annan hash stoppar kopieringen.
