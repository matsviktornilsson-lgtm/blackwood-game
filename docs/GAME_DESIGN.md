# BLACKWOOD — THE LAST REFUGE
## Game Design Document · v0.4 · 2026-11-06

> Living design document. Unless explicitly marked as a core direction, all mechanics, names and numbers are provisional.

## 1. Vision and premise
An atmospheric dark-fantasy **isometric tower defence + light colony survival** game. For generations humans have lived high above the forest in rooms **excavated directly into immense natural cliff faces**. At night, werewolves emerge from the forest to hunt them. Build a functioning community within the mountain while defending windows, shafts, galleries and access points against escalating waves.

**Emotional promise:** The mountain is humanity's last refuge. Every glowing window represents real people. Night brings dread and unseen threats rather than a colorful arcade battle.

## 2. Core pillars
1. **Verticality** — enemies climb, leap and exploit irregular rock routes at different heights. Attacks may bypass a lower defence and threaten higher openings.
2. **Darkness** — visibility is a gameplay resource; forest, mist, fog, torchlight, searchlights and moonlight shape targeting and warning times.
3. **Inside the mountain** — a connected, expandable settlement of excavated rooms supports the defence.
4. **Day/night loop** — deliberate construction and staffing by day; increasingly dangerous automated defences and tactical intervention by night.
5. **Atmospheric coherence** — cold rock and shadow; warm light leaking through high, barred windows; pine forests below; restrained UI, sound and animation.

## 3. Visual identity / non-negotiable art guardrails
- Enormous **natural, geological rock face**, irregular cracks and ledges, asymmetrical erosion and no repetitive man-made striation.
- The rock should dwarf the architecture; living and defensive chambers are **carved inside the mountain**.
- Glowing windows, galleries, grilles, apertures, hidden passages, mechanisms, supports and tunnels are fine.
- **Absolutely no external castles, keeps, turrets, battlements, parapet walls, fairy-tale towers or palaces.** This is a cliff-dwelling civilization, not a castle built upon a cliff.
- Dark evergreen forest, deep drop, blue-gray cold night, warm dim interiors, drifting mist; horror through suggestion and scale.
- A coherent architectural language: rugged, functional, assembled from excavations and modest metal/timber supports.
- 2D side-on and full 3D remain historical alternatives; **isometric is now the preferred view**, exact camera angle undecided.

## 4. Spatial design: the mountain as level
### Outer face / front layer
Openings carved into the cliff house crossbows, ballistae, lamps, oil-release points, traps, reinforced window grilles and observation stations. Climbing routes vary by topology. Lower, middle and upper heights each have tactical advantages and liabilities.

### Inner mountain / deep colony
Behind the exposed outer face, excavate and link rooms through corridors and shafts. Create kitchens, food storage, housing, infirmaries, workshops, forges, water facilities, stores and social spaces. Logistics and available personnel constrain outer defence.

### Recommended presentation (not finalized)
**Isometric sectional cutaway / dollhouse view:** show exterior cliff and selectively expose rooms behind it. Camera can pan and zoom along rock. Potential alternative: toggled inner/outer layers or dynamic wall-fade. Must preserve readable enemy paths and build locations.

## 5. Core gameplay loop
**Day — preparation:** review previous night's damage/casualties; treat wounded; ration food; excavate, construct and connect interior rooms; repair grilles; make ammo; place and upgrade defences; assign workers; observe forecasts; deliberately start night when ready.

**Night — defence:** werewolf packs emerge from concealed forest approaches and climb, jump, flank and attack openings. Weapons mostly act autonomously, with possible tactical intervention (exact interaction TBD). Detection depends on lighting, fog and enemy characteristics. A breach threatens not just abstract hit points but occupants, production and connected rooms.

**Dawn — consequences:** record injuries, losses, damaged structures, exhausted stores and resources earned/scavenged; reassess priorities and expand. Difficulty escalates across nights with special events and new enemy behaviors.

Target illustrative pacing: 3–5 minutes per early-night assault, untimed day preparation. Test and revise.

## 6. Combat and defence
Proposed exterior structures:
| Defence | Purpose | Upgrade possibilities |
|---|---|---|
| Crossbow emplacement | Accurate, affordable primary fire | reload speed, range, silver bolts |
| Ballista | Slow, heavy damage, penetration | armor penetration, multiple targets |
| Burning oil | Area denial along a climbing path | duration, spread, capacity |
| Torch / searchlight | Reveal or impede threats, support targeting | coverage, intensity, reliability |
| Reinforced grilles | Delay or prevent breaches into excavated rooms | durability, silver reinforcement |
| Rockfall trap | Devastating one-shot path attack | trigger control, resets |

Position, ammunition, personnel, sight lines and access must matter more than simple DPS. Defensive upgrades must trade off against living needs.

### Enemy archetypes (provisional)
- **Climber:** fast basic werewolf moving in packs.
- **Brute:** slow, powerful breacher capable of smashing barred windows.
- **Stalker:** conceals movement within fog and dark.
- **Alpha:** coordinates or buffs a pack, potentially redirects attacks toward weak sectors.

Pack behaviour may adapt to heavily defended routes, but should remain readable and telegraphed rather than arbitrary. Cliff geometry must allow understandable tactical prediction.

## 7. Darkness, light and moon
The player cannot see every enemy at all times. Unlit forest and climbing areas are hidden or poorly visible; lit enemies become targetable. Lights consume build capacity and possibly fuel/power; loss of lighting can blind adjacent defences. Sound, silhouette and reflected eyes foreshadow threats.

**Full moon hypothesis:** stronger wolves but better natural visibility. Weather and fog can vary detection without fully hiding necessary tactical information. Validate visibility and fairness early in prototyping.

## 8. The internal colony
Two connected layers, not two disconnected games:
- **Front layer**: exposed combat rooms, ammunition handling, observation, mechanism rooms, repairs.
- **Deep mountain**: food, water, habitation, healthcare, manufacturing, research, training and morale.

### Support buildings
| Building | Job / direct link to survival and defence |
|---|---|
| Housing / dormitory | Population capacity; rest, recovery, available labour |
| Food storage | Stores rations needed to sustain staffed defences |
| Kitchen | Converts food supplies into meals; improves recovery/morale |
| Well / reservoir | Provides and buffers essential water |
| Infirmary / hospital | Treats wounded defenders; reduces lasting workforce losses |
| Quarantine / shelter | Potential infection and serious injury response (later feature) |
| Forge | Produces metal components, weapons and grille repairs |
| Workshop | Builds traps, launchers, mechanisms and maintenance parts |
| Ammunition store | Holds produced bolts and ammunition; can bottleneck long assaults |
| Stonecutters / excavation workshop | Expands usable interior and creates rooms |
| Lookout / signal chamber | Reveals attack information and improves early warning |
| Archive / research room | Unlocks technology, silver weapons, lighting and medical improvements |
| Training hall | Improves staffing, hit rate, reload and repair competence |
| Assembly hall / chapel | Raises morale and recovery; counters panic |
| Underground food production / mushroom farming | Long-term sustainable food option |

All buildings are candidates, not commitments to complex production chains. Internal placement, links and proximity should eventually matter, but **do not create a full RimWorld/Dwarf Fortress-style individual-needs simulation** in the initial scope.

### Internal-to-external feedback
Hospital → faster defender return; kitchen and stores → sustainable staffing; forge/workshop → repair and ammo; lookout → forewarning; training → weapon efficiency; excavation → new chambers/openings; morale → reduced debuffs. Each building needs a legible, consequential game effect.

### Starter MVP internal buildings (proposal)
**Housing, Food Store, Infirmary, Forge, Workshop, Lookout/Signal Chamber.** The first prototype may implement only a subset to establish the feedback loop.

## 9. Economy and risk
Initial simple resources: **stone, iron, silver, food/supplies**. Water, medicine and labour might be tracked as capacities rather than separate inventory. Material balance and amounts TBD.

Future possibility: risky daylight expeditions down toward the hostile forest to gather scarce resources. Losses should change the next night's readiness. Avoid sprawling logistics at first.

## 10. Progression and example opening arc
Provisional first ten nights:
- Nights 1–2: small packs and basic crossbows.
- Nights 3–4: multiple climbing paths and split attacks.
- Night 5: first Brute and grille damage.
- Nights 6–8: fog, darkness and detection pressure.
- Nights 9–10: Blood Moon assault and an Alpha.

Expansion unlocks new rock sectors, more complex room networks, defences, research and special wave conditions. Campaign vs endless vs roguelite progression remains open.

## 11. Loss, damage and stakes
A successful breach may injure/kidnap/kill occupants, disable room production or damage linked infrastructure. Avoid a single HP bar where possible. Defeat conditions, rebuilding rules and whether a run can be salvaged remain open.

## 12. Audio / UX / feel
Day: chisels, hammering, distant voices, steady fire and the mountain wind.
Dusk: work ceases, wolf howls, isolated footsteps, wood creaking.
Night: claws on stone, metal grilles under strain, mechanical launches, sporadic calls from inside.
Restrained effects; no saturated explosions or crowded floating combat numbers. UI should show threat levels and visibility without sacrificing dread.

## 13. Prototype / vertical slice
Minimum slice goals:
1. One irregular natural cliff segment and two or three independently attackable apertures.
2. Traversable werewolf climbing routes with height and path choice.
3. Basic crossbow, grille and one lighting mechanic.
4. Climber and Brute enemies.
5. A simple day/night transition and ~5 increasing waves.
6. A tiny interior cutaway with at least one support-room effect.
7. Camera pan/zoom and legible fog-of-war / detection.
8. Track damage, wounded and repair resources.

The first build targets the **web browser on Cloudflare**. Its prototype stack is TypeScript, Three.js and Vite, with a 3D world shown through an orthographic isometric camera. Prototype geometry is created in code, so Blender is optional. Validate the cutaway, enemy routes, lighting, browser performance and file size before investing in detailed art. See [TECH_STACK.md](TECH_STACK.md). No implementation decisions are implied by the concept imagery.

## 14. Scope / principles
Tower defence is the primary loop; internal settlement makes the defence consequential. Maintain intuitive mechanics, constrained resources and readable choices. All values and building lists need playtesting.

See [OPEN_DECISIONS.md](OPEN_DECISIONS.md) for unresolved choices and [PERSPECTIVE_COMPARISON.md](PERSPECTIVE_COMPARISON.md) for view trade-offs.
