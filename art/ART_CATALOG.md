# Blackwood — Art Reference Catalog

> **Asset status:** Descriptive catalog created from the design conversation. Original raster image files have **not yet been transferred into this GitHub repository**. Do not interpret a filename below as an existing GitHub asset. This is a tracked upload/asset-generation manifest.

## Art direction — mandatory constraints
- The setting is a **natural, tall, rough, irregular mountain cliff** with human homes, tunnels, barred windows and defensive chambers **excavated into the cliff face**.
- **No castles, keeps, standalone watchtowers, battlement walls or external fortresses**. The cliff itself is the shelter.
- Warm amber light inside, cold blue-gray dusk or moonlight outside, dense conifer forests deep below, fog and tension.
- Random geological fractures and rough erosion: avoid regular linear or obviously manmade grooves.
- Isometric is the preferred gameplay camera; show the cliff **and interior cutaway rooms**. Other viewpoints are retained for comparison.

## Locally generated images from the conversation (pending GitHub binary upload)

| Proposed repository path | Original working filename | Subject | Use |
|---|---|---|---|
| `art/references/cliff-first-concept.png` | `Mountain Fortress Windows at Dusk.png` | High cliff with barred, warmly illuminated openings above dark forest | Original atmosphere reference; check latest art guardrails |
| `art/references/cliff-towering.png` | `fortress_in_the_towering_cliff.png` | Revision raising windows farther above forest | Scale and height reference |
| `art/references/cliff-irregular-rock.png` | `rugged_mountain_fortress_at_dusk.png` | Revision making cliff rock less repetitively patterned | Primary geological texture reference |
| `art/mockups/01-2d-side-view.png` | `01-2d-side-view.png` | 2D side-view tower defence test | Alternative perspective |
| `art/mockups/02-isometric.png` | `02-isometric.png` | Isometric gameplay mockup | **Preferred perspective reference** |
| `art/mockups/03-full-3d.png` | `03-full-3d.png` | Full 3D perspective mockup | Alternative perspective |
| `art/references/design-poster-a.png` | `a_wide_detailed_developer_design_doc_concept_po.png` | Design document concept poster | Presentation reference only, not a canonical GDD |
| `art/references/design-poster-b.png` | `a_detailed_concept_document_collage_in_a_cinematic.png` | Design collage | Presentation reference only |

**Note:** Some earlier generated reference visuals may still show castle-like structures. These are exploratory references and **must not override** the hard ban on castles.

## Images shown with the earlier design discussion (web/image-query illustrations; source binaries unavailable)

The illustrative images shown beside weapons, wolf types, support scenes and lighting were not preserved as project files. The concepts and captions are recorded here so that consistent, original game assets can be commissioned or generated.

### Enemies
| Concept | Visual brief | Gameplay role |
|---|---|---|
| **Climber** | Lean feral wolf-humanoid, long powerful claws, dark wet fur; climbing an uneven rock face in moonlight | Fast basic attacker, attacks in packs and seeks climbing paths |
| **Brute** | Massive broad-shouldered, dark-furred werewolf, visibly powerful forearms and jaws | Slow heavily damaging breacher that attacks metal-barred openings |
| **Stalker** | Sinewy pale/gray werewolf almost invisible in cold fog; subtle glint of eyes | Concealed approach, defeated by light/detection coverage |
| **Alpha** | Large scarred dominant werewolf, commanding posture amid other wolves; not a generic boss dragon | Commands or enhances pack behaviour; special wave threat |

### Defences and weapons
| Concept | Visual brief | Gameplay role |
|---|---|---|
| **Crossbow emplacement** | Practical mounted mechanical crossbow placed **inside a rock-hewn window**, not on a castle wall | Affordable precise basic ranged defence |
| **Ballista** | Heavy tension artillery mounted in a rocky excavated gallery | Slow, heavy, penetrating attack |
| **Burning oil** | Iron reservoir and pour-channel built into a high cliff aperture; hot fluid spilling down rock | Area damage / path denial |
| **Torches / searchlight** | Rock-mounted fire baskets, reflectors or mechanical lamp assemblies illuminating cliff and pine fog | Reveal enemies and support aiming |
| **Reinforced grille** | Thick iron bars inside crudely cut natural stone window, amber lamplight behind | Delay breaches, protect occupied rooms |
| **Rockfall trap** | Concealed boulders and release supports recessed into natural fractured cliff | One-use high-damage route attack |

### Interior colony building reference briefs
| Concept | Visual brief | Gameplay function |
|---|---|---|
| Housing | Modest hearth-lit chambers carved into rock | Rest, population, labor |
| Food store + kitchen | Stone shelves, hanging provisions, smoky ovens in an inner cavern | Rations and recovery |
| Infirmary | Wounded workers on beds under warm lamplight in a rock-cut medical chamber | Healing, avoid personnel loss |
| Forge | Small practical forge, bellows and tools inside excavated rock | Weapons, repairs and metalwork |
| Workshop | Workbenches and rough machinery in connected tunnels | Traps, mechanisms and ammunition |
| Lookout / signal room | Narrow tall cliff aperture with light hood / horn / signaling mechanism | Early warning, reveal attack routes |

### Environment / gameplay composition briefs
- **Exterior at dusk:** Cliff dominates frame, small warm windows high above vast evergreens.
- **Night assault:** Shrouded wolf eyes, mist, claws on cliff, lights gradually revealing climbing enemies.
- **Day building:** Workers repairing iron grilles, outfitting a window defence and tending interior life.
- **Cutaway isometric:** One coherent cliff section with a rocky exterior, defended apertures, connected tunnels and hospital/food/workshop rooms inside.

## Files / provenance
The generated raster files are from earlier image generations and locally staged mockups associated with this conversation. Image-query illustrations in previous explanatory messages were **visual suggestions**, not licensed or downloaded assets. Do not scrape arbitrary search images into a commercial game repository without rights clearance.

## Next action
Upload the eight original image files above into their listed paths; then replace “pending” with committed image links and verify all links render. Only then mark this task complete.

## Night Watch environment assets

The eight WebP textures in `web/src/assets/lookout/` were produced with the built-in ImageGen tool using `art/concepts/blackwood-cliff-lookout-first-person.png` as the visual reference. The four material tiles were cropped from one atlas and blended at the edges for tiling. The three spruce cutouts retain alpha transparency. The horizon texture is projected behind the 3D terrain.

### Material atlas prompt

> Transform the material language of the provided Blackwood reference into a production texture atlas, a clean top-down reference sheet of FOUR dense seamless physically plausible PBR BASE COLOR material tiles. Output one square 2x2 edge-to-edge image. The quadrants must meet precisely at the image midpoint with no padding, black lines, borders, perspective, labels or typography. Each square is a different complete tile. Top-left: dark neutral charcoal grey naturally fractured layered slate bedrock, fine and large crags, slightly damp, with flat neutral lighting and no baked directional shadows, no stones arranged like masonry. Top-right: gray weathered worn flat slate floor stone with shallow fissures, eroded pits, faint moisture streaks, flat neutral lighting. Bottom-left: dark brown rough-sawn old timber, long irregular grain running vertically through the whole tile, weathered and rubbed, no seams between planks, no painted finish. Bottom-right: forest floor at close range from directly overhead, dark brown soil, scattered low moss, small slate chips and dry spruce needles, flat lighting. Photoscan realism, high-frequency detail, texture fills every quadrant. Avoid bluish and orange lighting in the atlas since this will come from the 3D lights. This is for UV-mapped materials in the Blackwood playable 3D game. No scene or objects other than the four material surfaces.

### Horizon prompt

> Recompose the sky and the furthest horizon from the provided Blackwood first-person concept art into one wide cinematic distant matte painting for the playable 3D game's sky. View from above a remote mountainous spruce valley at midnight. Only the distant layers and the sky: dark, textured rolling storm clouds with subtle blue moonlight, a small pale full moon centered at 61% from the left and 35% down from the top, and low silhouettes of distant jagged mountain ranges far away mainly in the lower quarter of the image, sinking into cold deep blue haze. The dark sky should fill roughly the top 72 percent. The bottom should dissolve into smooth dark desaturated blue fog, with distant ridges and absolutely no foreground trees. Use the reference's muted cold navy, slate blue and charcoal tonal range and realistic cinematic painting. Keep cloud detail fine, with restrained moon bloom. Use an ultrawide horizontal composition, no room, cave, frame, rock arch, architecture, game UI, text, animals, human figures or lettering. This is a far background sky texture behind actual 3D forest and terrain.

### Spruce cutout prompt

> Create a production game asset sheet of exactly THREE separate full-height mature spruce tree cutouts for Blackwood. Use the spruce silhouettes in the attached concept image as the style and species reference. Transparent background with a clean true alpha channel. A wide horizontal image divided conceptually into three equal-width columns, one entire centered tree per column, generous transparent margin around each tree, no overlapping branches between columns, all root bases horizontally aligned at about 96 percent of the image height. Left is a dense Norway spruce, center is a taller and more irregular old spruce with open ragged boughs, right is a slightly windswept narrow spruce. Each is viewed from a modestly elevated lookout angle, seen as a natural whole tree, accurate botanical silhouettes with many fine drooping boughs and layered needle textures, visible narrow trunks at the bottom. Quiet photorealistic environment game asset, neutral low-contrast charcoal green with cool gray detail, no baked hard side lighting, no ground, no shadows outside the trees, no room, no sky, no lettering, no labels. These cutouts will be placed far away in a real 3D nighttime forest.

## Werewolf surface materials

The four WebP tiles in `web/src/assets/werewolf/` were generated with the built-in ImageGen tool using `art/promotional/blackwood-promo-no-text.png` and `inspiration/ChatGPT Image Nov 6, 2026, 07_11_55 AM.jpg` as references. The tiles were cropped from the atlas, blended at the edges for tiling, and mapped onto the animated Three.js model.

### Werewolf material atlas prompt

> Create a square 2 by 2 PBR base-color texture atlas for the werewolf creature in Blackwood. Use the attached Blackwood scene and creature concept as references for color, coarse wet fur and naturalistic horror. The atlas must be split exactly at the midpoint of both axes, with no gutters, labels, text, lighting gradient or visible borders. These are macro material samples, not pictures of animals or parts. Top left: layered charcoal-gray and brown-black coarse wolf guard hair, damp matted clusters and occasional muted ash tips, sweeping consistently down the tile. Top right: dense short dark gray hair from around a real wolf's muzzle and eye sockets, fine fur following the same vertical flow, sparse warmer gray fibers, no face features. Bottom left: pebbled dark gray canid nose leather and weathered hide, irregular micro folds and subtle pores, desaturated and dark. Bottom right: rough unkempt smoky gray-black underfur with tangled coarser silver-gray hair at low contrast, still dark like the concept. Orthographic flat neutral scan lighting, realistic natural texture, moderate exposure so fine fiber detail survives game lighting, high-frequency detail. No ears, eyes, teeth, silhouettes, props, seams between swatches or baked shadows.
