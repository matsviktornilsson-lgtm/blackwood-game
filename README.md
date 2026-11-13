# Blackwood — The Last Refuge

**Night Watch** is the first playable browser test. Spend 30 seconds building in a carved lookout, then defend it for 60 seconds as werewolves keep coming through the forest. Survive the watch to build again at dawn. See the [playtest controls](web/README.md) and [first-person concept art](art/concepts/blackwood-cliff-lookout-first-person.png).

An atmospheric isometric dark-fantasy **tower defence + light colony survival** game. Humans have retreated into homes, workshops and defensive chambers **excavated into enormous natural cliffs** above a forest inhabited by hunting werewolves. By day, develop the settlement and prepare. By night, defend its openings against increasingly dangerous climbing packs.

## Core design pillars

1. **Verticality:** Attacks move upwards over real rock faces; multiple elevations, routes and openings.
2. **Darkness and visibility:** The forest is dangerous and largely unseen; lighting, fog, moonlight and detection affect combat.
3. **The mountain is home:** Explore and construct inhabitable chambers and logistical systems deeper inside the cliff.
4. **Meaningful support systems:** Food, housing, hospitals, workshops and training directly influence defence.
5. **Atmosphere:** Enormous irregular natural stone, dark fir forests, mist and warm light from inhabited excavations.

**Art direction — essential:** NO castles, keeps, battlements, freestanding medieval towers or exterior castle walls. Human architecture consists of **windows, iron grilles, tunnels, galleries, rooms, timber reinforcements and weapon embrasures carved into natural rock**. The cliff remains overwhelmingly natural, geologically irregular and gigantic.

## Documents

- [Game Design Document](docs/GAME_DESIGN.md)
- [Outstanding design choices](docs/OPEN_DECISIONS.md)
- [Perspective comparison](docs/PERSPECTIVE_COMPARISON.md)
- [Technical stack and Blender-free workflow](docs/TECH_STACK.md)
- [Windows-native creature model pipeline](docs/MODEL_PIPELINE.md)
- [Visual inspiration](inspiration/README.md)

## Current decisions

The current playtest uses a **first-person perspective** for the night watch. The isometric view remains a candidate for daytime colony management. The design documents describe the earlier tower-defence concept. The target is a **browser game deployed on Cloudflare**. The playtest uses TypeScript, Three.js and Vite.

## Planned layout

```text
blackwood-game/
├── README.md
├── .gitignore
├── docs/
│   ├── GAME_DESIGN.md
│   ├── OPEN_DECISIONS.md
│   ├── PERSPECTIVE_COMPARISON.md
│   └── TECH_STACK.md
├── art/
│   └── promotional/
├── inspiration/
└── web/                  # Browser prototype; Vite builds to web/dist/
```

Run the web prototype from `web/` with `npm ci` and `npm run dev`. Build with `npm run build`; Cloudflare Pages can serve `web/dist/`. The images are concept and promotional references, not implemented gameplay.

For creature production, run `./art/tools/blackwood.ps1 doctor` from the repo root in PowerShell 7. See the [migration report](docs/MODEL_PIPELINE_MIGRATION.md) for the missing workflows and native components.
