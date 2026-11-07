# Blackwood — web-first technical stack

**Decision date:** 2026-11-06. Target: a browser game deployed on Cloudflare.

## Chosen stack

| Area | Choice | Reason |
| --- | --- | --- |
| Language and build | TypeScript + Vite | Fast local iteration and a static production bundle. |
| 3D rendering | Three.js with an orthographic camera | The cliff, cutaway and climbing routes retain real depth while the view reads as isometric. |
| UI and sound | HTML/CSS and browser audio | Keep menus and status readable without a second UI framework in the prototype. |
| Hosting | Cloudflare Pages with Git integration | Static `web/dist/` output can be built from the GitHub repo. |
| Saves | Browser-local storage initially | No account or server is needed for the first playable slice. |
| Art | Simple procedural geometry and materials | Blender is optional, not a prerequisite. |

This replaces the earlier Godot 4 PC-first proposal. Godot 4 web export supports only the Compatibility renderer, while Cloudflare Pages has a 25 MiB limit per static asset. A stock Godot WebAssembly engine can exceed that limit before game assets are added. The web-native stack avoids that deployment obstacle. We can reconsider the engine if a later prototype shows a reason to do so.

## Build and deploy shape

The browser app lives in `web/`. `npm run build` produces `web/dist/`; Cloudflare Pages should use `web` as the project root, `npm run build` as the build command and `dist` as the output directory. Connect the existing GitHub repo to Pages when there is a build worth publishing. The first prototype needs no Worker, database or R2 bucket. Keep individual output files below Cloudflare Pages' 25 MiB limit and test load time on desktop and mobile browsers.

## No Blender requirement

Use simple shapes and reusable code modules to establish scale, camera, room selection, light and enemy routes. Detailed models can later come from a collaborator, licensed assets or any tool that exports glTF/GLB. The game code should not depend on a specific modeling program.

## First playable proof

One irregular cliff segment, two climbing routes, two interior rooms, a crossbow post, a grille, a light that reveals enemies, a few wolves, and a day/night transition. The earliest web scaffold may only prove rendering and controls; it is not a complete game. Success means the player can read enemy paths, rooms and lighting at normal browser zoom and the production bundle deploys within Cloudflare's limits.

## Sources

- [Godot web export and Compatibility renderer](https://docs.godotengine.org/en/4.5/tutorials/export/exporting_for_web.html)
- [Cloudflare Pages file limits](https://developers.cloudflare.com/pages/platform/limits/)
- [Cloudflare Pages build configuration](https://developers.cloudflare.com/pages/configuration/build-configuration/)
- [Vite static build](https://vite.dev/guide/build)
- [Three.js orthographic camera](https://threejs.org/docs/pages/OrthographicCamera.html)
