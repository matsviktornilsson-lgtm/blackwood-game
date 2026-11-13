# Windows-native modellpipeline

De ursprungliga Hermes-graferna och adaptrarna gick förlorade. Repot innehåller fyra ComfyUI-presets och två Blender-adaptrar med batch5:s inställningar och kontroller. [Huvudguiden](MODEL_PIPELINE.md) beskriver körordning och godkännanden.

## NewHomer

| Komponent | Verifierat |
|---|---|
| ComfyUI | `E:\AI-Native\apps\ComfyUI`. Loopback-GET på `127.0.0.1:8188` rapporterade ComfyUI 0.42.1, frontendkrav 1.55.18, Python 3.12.16 och torch 2.11.0+cu130. |
| Launcher | `E:\AI-Native\Start-ComfyUI.ps1` har whitelist för `hermes_model_state` och `hermes_archive`. De nya graferna använder noder som ComfyUI registrerar med den befintliga whitelisten. |
| Blender | `E:\AI-Native\tools\blender-4.2.9-windows-x64\blender.exe`. Adaptrarna använder Blenders Python, bmesh, NumPy och glTF-stöd. |
| Node | Portabel Node LTS 24.22.3 med npm under `E:\AI-Native\tools\node\`. |
| glTF Transform | CLI 4.5.1 under `E:\AI-Native\tools\gltf-transform\`. |
| Arbetsyta | `E:\AI-Native\workspaces\blackwood\runs` är den konfigurerade produktionsytan. Den har ännu inte skapats. |

`blackwood.config.local.json` anger maskinens absoluta programsökvägar och repots nya grafer och adaptrar.

## Modellfiler för ComfyUI

| ComfyUI-mapp | Filnamn som graferna väntar på |
|---|---|
| `models/diffusion_models` | `flux1-dev.safetensors` (laddas med `fp8_e4m3fn`), `flux1-schnell.safetensors`, `trellis_2_int8_convrot.safetensors` |
| `models/text_encoders` | `clip_l.safetensors`, `t5xxl_fp8_e4m3fn.safetensors` för dev, `t5xxl_fp16.safetensors` för Schnell |
| `models/loras` | `flux-realism-lora.safetensors` är det lokala filnamnet för XLabs AI:s publicerade `lora.safetensors` |
| `models/vae` | `ae.safetensors`, `trellis_2_shape_vae_bf16.safetensors`, `trellis_2_texture_vae_bf16.safetensors` |
| `models/clip_vision` | `dino_v3_L_naf_fp32.safetensors` |
| `models/background_removal` | `birefnet.safetensors` |

Se modellkällorna för licensvillkor och filversioner innan de hämtas. `doctor` jämför namnen med serverns modellistor. [ComfyUI:s Flux-mall](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/flux_schnell_full_text_to_image.json) · [ComfyUI:s TRELLIS.2-guide](https://github.com/Comfy-Org/docs/blob/main/tutorials/3d/trellis2.mdx)

Mats har valt att tillämpa FLUX.1 dev-licensens utdataregler som tillåter kommersiell användning av genererade bilder enligt villkoren. Själva modellen omfattas av icke-kommersiell licens. XLabs märker även LoRA-filen med FLUX.1 dev-licensen. [Black Forest Labs licens](https://huggingface.co/black-forest-labs/FLUX.1-dev/blob/main/LICENSE.md) · [XLabs Realism-LoRA](https://huggingface.co/XLabs-AI/flux-RealismLora/blob/4fc8d2fc5f65e3f22b2b59738807b8b4d1bc56ee/lora.safetensors)

## Adapterkontrakt och rapporter

- `make_game_glb.py -- --raw <källa> --output <glb> --previews <mapp> --report <json>` körs i bakgrunds-Blender. Collapse kräver unika trianglar, ytterlägen inom 2 % av höjden och IoU ≥ 0,95 fram och sida. Annars provas CuMesh 512 i konfigurerad TRELLIS-Python, med ComfyUI-Python som standard för den inbyggda TRELLIS-installationen. Vid saknat CuMesh/CUDA används Blender-voxel 4 mm. Skalvägen behåller den största slutna komponenten, gör en ny Smart UV-atlas och bakar diffus RAW-färg med cage. Rapporten anger vald väg, mätvärden, bake-inställningar och varför eventuell voxelväg valdes. [Microsofts CuMesh-remesh i TRELLIS.2](https://github.com/microsoft/TRELLIS.2/blob/main/o-voxel/o_voxel/postprocess.py)
- `bake_scene.py -- --game <glb> --image <frilagd-png> --output <glb> --previews <mapp> --report <json>` anpassar ortografisk skala och förskjutning efter alfasilhuettens IoU. Rapporten anger fullupplöst IoU och konturavstånd (p95 och max). Färgen projiceras från +Z med djupbuffert, cirka 4 px alfakant, vinkeltoning och 16 px atlaspadding. Texlar som delas av olika ytor behåller tidigare färg. Adaptern jämför geometri, UV och scen-/nodtransform efter export, behåller metallic/roughness och rensar AO, normalkarta och överblivna bilder. Den stöder en statisk inbäddad GLB med en mesh, en primitiv, en standard-PBR-materialplats och en normaliserad UV-atlas.
- Båda körs med argumentlistor och adapterns katalog som cwd. `blackwood.ps1` kontrollerar källans SHA-256 före och efter, kopplar resultatet till körning, seed och batch och skapar en hashad fillista för publicering.

Ett förkortat GAME-rapportexempel med fiktiva värden:

```json
{"raw_triangles": 84000, "game_triangles": 39800, "height_m": 2.2,
 "unique_triangles": true, "extremities_present": true,
 "extremity_probes": {"left_arm": {"source_vertices": 500, "game_vertices": 120, "extent_delta_m": 0.01}}}
```

Ett förkortat projektionsrapportexempel med fiktiva värden:

```json
{"geometry_preserved": true, "uv_preserved": true, "transform_preserved": true,
 "projected_texels": 135420, "triangles": 39800}
```

## Verifiering och nästa godkännande

Batch5 GAME och godkänt facit har vardera 39 257 trianglar. Facitets SHA-256 matchar överlämningsmanifestet och materialet saknar AO- och normalkarta. Den historiska [projektionsrapporten](../3d/incoming/batch5/20261110-131747/manifest.json) anger fullupplöst IoU 0,8419, p95 29,7 px och max 98,1 px. Den exakta källbilden identifieras som `_evidence/1d6b1086-d574-4f26-b5f0-00e011a653f1/cutout_00001_.png`. Varken den eller batch5 RAW hittades på de läsbara Windows-sökvägarna. Därför hoppades båda körproven över. Historiska mätvärden är referens för nästa körning.

Repoarbetet och fixturverifieringen ligger på acceptansnivå 1. 15 pipeline-fixturer, 7 NumPy-fixturer och TypeScript/Vite-bygget passerade. De fyra graferna kontrollerades mot den installerade serverns nodscheman med modellvalen simulerade. Live-`doctor` bekräftade att Dev-, Schnell- och LoRA-vikterna som graferna anger saknas. Blender och CuMesh kördes inte under verifieringen. Modellhämtning och ny Flux- eller TRELLIS-generering väntar på Mats godkännande. Kandidaten granskas i Modellabbet före riggning och i spelet före standardbyte.

Den externa inventeringen `C:\Users\tuxol\Desktop\Blackwood - var allt ligger.md` beskriver den tidigare kedjan. Använd repots huvudguide för de aktuella kommandona.

## GPU-verifiering på NewHomer

Flux Dev och TRELLIS.2 512³ har körts på RTX 4090. Bild 2:s RAW är sparad med 1 139 622 trianglar. CPU-varianten av UV-segmenteringen fastnade på den täta modellen. De aktiva TRELLIS-presets använder nu PEC på GPU.

Verifieringsproverna i `build/blackwood/gpu-verify-batch2` visar CUDA för Flux, TRELLIS och projektion samt OptiX för Blender-bakning, förhandsbilder och riggdiagnostik. Riggvikter, komprimering och filkontroller körs på CPU. Under det isolerade Blender-baket uppmättes upp till 96 % belastning och 10 058 MiB använt grafikminne på kortet. VRAM-värden för ComfyUI gäller de senare verifieringsproverna.

Den första voxelversionen av GAME för bild 2 nådde 119 182 unika trianglar och sparades för diagnos. Windows-CuMesh är nu konfigurerat i en separat paketkatalog. Revideringen med 60° normalutjämning gav 37 501 trianglar och projektionen nådde IoU 0,910. Båda publicerades i Modellabbet.
