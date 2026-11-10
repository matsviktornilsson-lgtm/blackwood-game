# Batch 5 v3 · riggdiagnos

Indata är `3d/incoming/batch5-diag/20261110-134907/batch5_utan_ao_och_normal.glb`, godkänd i modellabbet av Mats. Modellen bygger på Batch 5 GAME (Flux-seed `2685697290443443`, TRELLIS.2 med MIT-licens) med konceptbildens färg projicerad på framsidan. Indata har samma 39 257 trianglar i samma positioner som Batch 5 GAME, med markplanet vid Y = 0 och en höjd på 2,20 m.

```sh
blender --background --python-exit-code 1 --python art/creatures/rig_generated_wolf.py -- 3d/incoming/batch5-diag/20261110-134907/batch5_utan_ao_och_normal.glb build/wolf-v3/ledge-wolf-v3-fitted.glb --fit-puppet
```

Blender 4.2.23 LTS exporterade 19 ben. Ledernas lokala positioner och rotationer är identiska med v2, inklusive båda handlederna och käkleden relativt skallen. Alla vertexar är viktade, med högst fyra influenser per vertex. Käkbenet påverkar 743 vertexar.

I testposen med 60° armbågsböjning behåller händer och klor formen och följer underarmarna. Vid 25° käköppning följer underkäken leden medan nosen ligger kvar. Den sammanvuxna främre läppen sträcks fortfarande vid öppning, som på Batch 5.

Skriptet skriver vilopos och testpos till `build/wolf-v3/ledge-wolf-v3-fitted-diagnostics/`. För kontrollen användes särskilt `test-front.png`, `test-side.png` samt paret `rest-jaw.png` och `test-jaw.png`. BaseColor och metallicRoughness bevarades byte för byte genom riggningen.
