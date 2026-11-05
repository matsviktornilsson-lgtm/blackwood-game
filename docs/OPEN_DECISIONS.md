# Blackwood — Outstanding Design Decisions
**Status:** Living backlog · 2026-11-05. Decisions can be revisited.

Legend: **Direction** = current preference, **Open** = not chosen, **Prototype** = test before locking.

| ID | Area | Status | Options / question | Current recommendation |
|---|---|---|---|---|
| D01 | View | **Direction** | 2D side / isometric / full 3D | **Isometric** (preferred after mockup comparison); exact implementation uncommitted |
| D02 | Mountain reveal | **Open** | sectional cutaway / interior-exterior toggle / adaptive transparent rock | Prototype cutaway first |
| D03 | Camera | **Open** | fixed isometric angle / limited orbit / freely rotatable 3D | Fixed or limited rotation initially, pan and zoom |
| D04 | Combat control | **Open** | automatic defence / hybrid commands / manual aiming | Primarily automatic with limited tactical controls |
| D05 | Overall mode | **Open** | story campaign / endless survival / roguelite | Campaign with optional survival mode |
| D06 | Building layout | **Open** | fixed sockets / free excavation grid / room templates | Excavatable room grid with selected exterior sockets |
| D07 | Worker simulation | **Open** | aggregate workforce / named settlers / individual needs | Aggregate workforce, injuries and staffing |
| D08 | Resources | **Open** | stone, iron, silver, food / add water, wood, fuel, medicine | Start with 4 and treat some as capacities |
| D09 | Supply logistics | **Open** | global inventory / local storage / corridor travel time | Global stock MVP, add meaningful proximity later |
| D10 | Light & sight | **Prototype** | fog of war, line of sight, lamp fuel, moonlight | Make visibility key; test fair readable detection |
| D11 | Werewolf AI | **Prototype** | fixed routes / dynamic climbs / adaptive pack targeting | Multiple telegraphed climbing routes and limited adaptation |
| D12 | Breach consequences | **Open** | single core HP / room damage & casualties / infiltration | Functional room damage and wounded workers |
| D13 | Colony management depth | **Direction** | tower-defence-only / light colony / full sim | **Light colony supporting defence**, not full RimWorld |
| D14 | Initial support rooms | **Prototype** | 6-room set vs smaller starter set | Housing, food store, infirmary, forge, workshop, lookout |
| D15 | Night pacing | **Prototype** | timed prep / free prep, 3–5 min nights / continuous time | Player-triggered night, short initial assault |
| D16 | World structure | **Open** | single expanding cliff / multiple sites / campaign map | Single persistent cliff for MVP |
| D17 | Technical stack | **Open** | Godot 4 / Unity / other | Spike Godot 4; confirm isometric cutaway and lighting |
| D18 | Art production | **Open** | 2D painted / 2.5D layered / low-poly 3D with cinematic lighting | Test stylized 3D scene with fixed isometric camera |
| D19 | Expedition mechanic | **Open** | abstract event / staffed mission / playable exterior | Defer, possibly abstract daylight missions |
| D20 | Victory and defeat | **Open** | survive nights / preserve population / objective-based | Define after first combat loop works |
| D21 | Difficulty | **Open** | authored waves / procedural waves / hybrids | Authored first 10 nights, then hybrid |
| D22 | Release platforms | **Open** | PC-first / desktop and handheld / web | PC-first until performance target chosen |
| D23 | Naming | **Open** | Blackwood / The Last Refuge / new title | Working title only |

## Agreed creative constraints
- **Never depict exterior castles or built fortress towers.** All human shelter and defensive architecture is excavated into natural rock.
- Naturally chaotic, geologically credible cliff surface; enormous height over a dense conifer forest.
- Warm lived-in chambers, cold moonlit exterior, fog, darkness, unsettling audio.
- Vertical werewolf climbing and darkness are core mechanics, not mere background.
- Interior rooms (hospital, food, living spaces, workshops) must have game consequences for exterior defence.

## Next decisions to prototype, in order
1. Build small isometric **exterior + interior cutaway** scene to test legibility of heights and access.
2. Test darkness / light reveal and cliff-climbing routes.
3. Decide exterior build sockets versus free excavation.
4. Test tiny colony economy (infirmary + food storage + workshop) and injuries.
5. Confirm camera and engine after hands-on prototype.

Record decisions here, moving items to a dated decision log once settled.
