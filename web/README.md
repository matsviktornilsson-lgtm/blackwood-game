# Blackwood — Night Watch

The first playtest takes place at a fixed lookout inside the cliff. You start with 20 coins, 100 health, and 30 seconds to build before the first Night Watch. Survive 60 seconds as werewolves keep emerging from the mist and advancing through the trees. Each kill earns 10 coins. At dawn, review the watch summary, then continue to the next 30-second build phase. Injuries carry over. First aid restores up to 35 health for 20 coins during building. Listen for claws on the rock. A werewolf that reaches the ledge raises its head and growls, then roars and lunges into the lookout. You can shoot at close range.

```sh
npm ci
npm run dev
```

- Move the mouse to look around. Drag in the scene if the browser leaves the pointer unlocked.
- Left-click to shoot. Right-click or press Q to raise or lower the scope.
- Press R to reload the single-shot rifle after each shot. Press Esc to pause the night.
- Press M to toggle the music. Sound effects play independently.
- Build only between watches. Buy ammo, a faster bolt, first aid, barricades, or tripwire bells. Each bell warns you when a werewolf starts climbing its lane and stays armed for the run. Start the watch early with the button or wait for the build timer to run out.

`npm run build` type-checks the game and builds the static site in `dist/`.

## Generated werewolf rig preview

The Phase 1 source in the local `3d/` folder is `2026-11-09_2685697290443443_batch5_game.glb`. It came from a Flux concept passed through [TRELLIS.2](https://github.com/microsoft/TRELLIS.2), which releases its model and code under the MIT license.

Use the [native model pipeline](../docs/MODEL_PIPELINE.md) from the repository root. After approval in the Model Lab, run this in PowerShell 7 with a configured Windows Blender:

```powershell
./art/tools/blackwood.ps1 rig --source '3d/2026-11-09_2685697290443443_batch5_game.glb' --output 'build/batch5-rigged.glb' --approved
```

The script writes the skinned GLB and a sibling `batch5-rigged-diagnostics/` folder with the joint and weight report and images of both poses. The landmark guides were traced on Batch 5. Review them before running the script on a different sculpt. The export stays separate from the game asset while the rig is under review.

Add `--fit-puppet` to export the fitted version. This reshapes the skin to the existing climb and attack joints and keeps the generated jaw hinge in the skull. The optional `LEDGE_MODEL_EVERYWHERE` constant in `src/wolf-ledge-model.ts` enables v2 on the forest approach for performance testing.

The game defaults to the approved v3 model. Use `/?preview=ledge-wolf` to see it during the ledge attack. Add `&wolf=v2` or `&wolf=v1` to preview an earlier version. If v3 fails to load, the game tries v2 and then v1. The [v3 rig report](../art/creatures/batch5-v3-rig-report.md) records the source and diagnostic poses.

To stage a new asset, use a fitted Blender export and choose the next free version. The native command uses the configured local glTF Transform CLI.

```powershell
./art/tools/blackwood.ps1 compress --source 'build/stalker-rigged.glb' --version 4 --approved
./art/tools/blackwood.ps1 build
```

WebP keeps the metallic and roughness map lossless and works with the existing loader. Draco compresses the geometry. The shipped v2 asset is about 4.70 MB.

## Audio credits

- Rifle shot and bolt action excerpts from [308_rifle_02.wav by gezortenplotz](https://freesound.org/people/gezortenplotz/sounds/43756/) under [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). The excerpts were trimmed and mixed for Blackwood. The bolt excerpts were retimed to match the reload.
- Cartridge insertion from [BoltLoad_01.wav by fastson](https://freesound.org/people/fastson/sounds/399119/) under [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). Bolt closing from [rifle_open+close breech(2).wav by beerbelly38](https://freesound.org/people/beerbelly38/sounds/362346/) under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Both were trimmed and retimed for the animation.
- Wolf howl excerpts from the [U.S. National Park Service recording at Denali](https://www.nps.gov/subjects/sound/sounds-wolf.htm). The recording is part of the [public-domain NPS Sound Gallery](https://www.nps.gov/subjects/sound/gallery.htm). The excerpts were trimmed and mixed for distance.
- Claw Foley from [Rock on Rock Scrape by Allan Legemaate](https://freesound.org/people/alegemaate/sounds/364709/) under CC0. Ledge growl from [wolf-growl.wav by newagesoup](https://freesound.org/people/newagesoup/sounds/338674/) under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Lunge roar from [Dragon: Snarl, Roar + Attack by Breviceps](https://freesound.org/people/Breviceps/sounds/466830/) under CC0. All three were trimmed and mixed for the game.
