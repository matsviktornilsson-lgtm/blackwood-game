import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { box, scatter } from './geometry';
import { groundTexture, horizonTexture, slateSurface, spruceSprites, weatheredWood } from './lookout-materials';

export const floorY = 18.4;
export const lookoutPosition = new THREE.Vector3(0, floorY + 2.02, 4.85);

const trails = [
  [[-38, -101], [-26, -78], [-17, -64], [-24, -49], [-12, -38], [-14, -24], [-8, -12]],
  [[38, -105], [23, -82], [30, -65], [18, -52], [23, -40], [12, -27], [8, -12]],
];

export function groundHeight(x: number, z: number) {
  return Math.sin(x * 0.064 + z * 0.037) * 2.1 + Math.cos(z * 0.13 - x * 0.095) * 0.8
    + Math.sin(x * 0.12 + z * 0.16) * 0.5 + Math.max(0, Math.abs(x) - 38) * 0.2
    + Math.min(10, Math.max(0, -z - 108) * 0.14);
}

const climbShelves = [
  [7.3, 4, -10.6],
  [6, 8, -9.3],
  [5, 12, -7.7],
  [3.8, 15.45, -5.65],
  [3.02, 16.43, -3.55],
  [2.54, 16.35, -2.13],
  [2.14, floorY - 2.10, -1.60],
] as const;

type ForestPoint = readonly [x: number, z: number];
type Spruce = { x: number; z: number; height: number };

function onGround([x, z]: ForestPoint) {
  return new THREE.Vector3(x, groundHeight(x, z), z);
}

function weavePastTrunks(route: THREE.CatmullRomCurve3, trees: readonly Spruce[]) {
  const samples = route.getSpacedPoints(Math.ceil(route.getLength() / 0.53));
  const last = samples.length - 1;
  const { lerp, smoothstep } = THREE.MathUtils;
  for (let pass = 0; pass < 3; pass++) {
    for (const tree of trees) {
      if (tree.z < samples[0].z || tree.z > samples[last].z) continue;
      // The approaches keep advancing in Z. Bracket the trunk to find the route at its depth.
      let low = 0;
      let high = last;
      while (high - low > 1) {
        const middle = (low + high) >> 1;
        if (samples[middle].z < tree.z) low = middle;
        else high = middle;
      }
      const before = samples[low];
      const after = samples[high];
      const pathX = lerp(before.x, after.x, (tree.z - before.z) / (after.z - before.z));
      const gap = pathX - tree.x;
      const clearance = tree.height * 0.026 + 0.88;
      const shift = clearance - Math.abs(gap);
      if (shift <= 0) continue;
      const direction = gap < 0 ? -1 : 1;
      const spread = 2.55 + shift * 0.7;
      for (let i = Math.max(0, low - 12); i <= Math.min(high + 12, last - 1); i++) {
        const falloff = 1 - smoothstep(Math.abs(samples[i].z - tree.z), 0, spread);
        samples[i].x += direction * shift * falloff;
      }
    }
  }
  for (const point of samples) point.y = groundHeight(point.x, point.z);
  const adjusted = new THREE.CatmullRomCurve3(samples);
  adjusted.arcLengthDivisions = samples.length * 4;
  return adjusted;
}

export function forestApproach(waypoints: readonly ForestPoint[], trees: readonly Spruce[]) {
  return weavePastTrunks(new THREE.CatmullRomCurve3(waypoints.map(onGround)), trees);
}

export function cliffEntry(footX: number, lipX: number) {
  const foot = onGround([footX, -12]);
  const climbingPoints = [
    foot,
    ...climbShelves.map(([x, y, z]) => new THREE.Vector3(
      THREE.MathUtils.lerp(lipX, footX, (x - 2.14) / (8 - 2.14)), y, z,
    )),
  ];
  const ledge = climbingPoints[climbingPoints.length - 1];
  const peek = new THREE.Vector3(lipX, floorY - 1.88, -1.51);
  const launch = new THREE.Vector3(lipX * 0.98, floorY - 0.90, -0.49);
  const landing = new THREE.Vector3(lipX * 0.60, floorY, lookoutPosition.z - 1.86);
  return {
    foot,
    climb: new THREE.CatmullRomCurve3(climbingPoints),
    ledge,
    peek,
    launch,
    lunge: new THREE.CubicBezierCurve3(
      launch,
      new THREE.Vector3(lipX * 0.95, floorY - 0.32, -0.19),
      new THREE.Vector3(lipX * 0.73, floorY + 0.96, 1.72),
      landing,
    ),
    landing,
  };
}

function trailDistance(x: number, z: number) {
  let nearest = Infinity;
  for (const points of trails) {
    for (let i = 1; i < points.length; i++) {
      const [ax, az] = points[i - 1];
      const dx = points[i][0] - ax;
      const dz = points[i][1] - az;
      const t = THREE.MathUtils.clamp(((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz), 0, 1);
      nearest = Math.min(nearest, Math.hypot(x - ax - dx * t, z - az - dz * t));
    }
  }
  return nearest;
}

function buildTerrain(scene: THREE.Scene) {
  const shape = new THREE.PlaneGeometry(380, 300, 142, 112).rotateX(-Math.PI / 2).translate(0, 0, -148);
  const positions = shape.attributes.position;
  const colors: number[] = [];
  const shade = new THREE.Color();
  const forest = new THREE.Color('#788d80');
  const clearing = new THREE.Color('#c0c3bf');
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i);
    const z = positions.getZ(i);
    positions.setY(i, groundHeight(x, z));
    shape.attributes.uv.setXY(i, x * 0.18, z * 0.18);
    const open = 1 - THREE.MathUtils.smoothstep(trailDistance(x, z), 0.85, 5.0);
    shade.copy(forest).lerp(clearing, open * 0.85).multiplyScalar(0.88 + scatter(i + 227) * 0.20);
    colors.push(shade.r, shade.g, shade.b);
  }
  shape.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  shape.computeVertexNormals();
  const terrain = new THREE.Mesh(shape, new THREE.MeshStandardMaterial({ map: groundTexture, vertexColors: true, roughness: 0.96 }));
  scene.add(terrain);
  return terrain;
}

function buildForest(scene: THREE.Scene) {
  const trees: Spruce[] = [];
  for (let i = 0; i < 2500; i++) {
    const x = (scatter(i + 2) - 0.5) * 218;
    const z = -13 - scatter(i + 3305) * 157;
    const opening = trailDistance(x, z);
    if (opening < 2.6 || (opening < 6.25 && scatter(i + 310) < 0.57)) continue;
    if (Math.abs(x) < 11 && z > -24) continue;
    trees.push({ x, z, height: 2.3 + scatter(i + 721) * 6.1 });
  }

  const transform = new THREE.Object3D();
  const trunks = new THREE.InstancedMesh(
    new THREE.CylinderGeometry(0.44, 1, 1, 5), new THREE.MeshBasicMaterial(), trees.length,
  );
  trunks.name = 'Spruce trunk colliders';
  trunks.visible = false;
  trees.forEach(({ x, z, height }, index) => {
    transform.position.set(x, groundHeight(x, z) + height * 0.41, z);
    transform.scale.set(height * 0.026, height * 0.82, height * 0.026);
    transform.updateMatrix();
    trunks.setMatrixAt(index, transform.matrix);
  });
  scene.add(trunks);

  const near = trees.filter(({ x, z }) => z > -52 && Math.abs(x) < 44);
  const far = trees.filter(({ x, z }) => z <= -52 || Math.abs(x) >= 44);
  for (let i = 0; i < 1050; i++) {
    far.push({
      x: (scatter(i + 7552) - 0.5) * 290,
      z: -168 - scatter(i + 5275) * 104,
      height: 3.0 + scatter(i + 7951) * 7.5,
    });
  }

  // The camera rotates from a fixed position, so each detailed spruce can face the lookout.
  const sprite = new THREE.PlaneGeometry(1, 1).translate(0, 0.5, 0);
  const tint = new THREE.Color();
  spruceSprites.forEach(({ map, width }, variant) => {
    const belongsToVariant = (_: unknown, index: number) => index % spruceSprites.length === variant;
    const group = [...far.filter(belongsToVariant), ...near.filter(belongsToVariant)];
    const material = new THREE.MeshBasicMaterial({ map, color: '#bfccd3', alphaTest: 0.39 });
    const canopy = new THREE.InstancedMesh(sprite, material, group.length);
    canopy.name = 'Spruce canopy';
    group.forEach(({ x, z, height }, index) => {
      const yaw = Math.atan2(lookoutPosition.x - x, lookoutPosition.z - z);
      const spread = z > -52 && Math.abs(x) < 44 ? 0.79 : 1;
      transform.position.set(x, groundHeight(x, z), z);
      transform.rotation.set(0, yaw, 0);
      transform.scale.set(height * width * spread, height, 1);
      transform.updateMatrix();
      canopy.setMatrixAt(index, transform.matrix);
      canopy.setColorAt(index, tint.setScalar(0.82 + scatter(index + variant * 113) * 0.18));
    });
    scene.add(canopy);
  });
  return { trunks, trees };
}

const slab = mergeVertices(new THREE.IcosahedronGeometry(1, 1).deleteAttribute('normal').deleteAttribute('uv'));
const rockVertices = slab.attributes.position;
for (let i = 0; i < rockVertices.count; i++) {
  const x = rockVertices.getX(i);
  const y = rockVertices.getY(i);
  const z = rockVertices.getZ(i);
  const seam = Math.sin(y * 9.5 + x * 1.4) * 0.081;
  const bulge = 1 + 0.14 * Math.sin(x * 7 + z * 3) + seam;
  rockVertices.setXYZ(i, x * bulge, y + seam + x * 0.12, z * bulge);
}
slab.computeVertexNormals();
function rock(parent: THREE.Object3D, material: THREE.Material, seed: number, x: number, y: number, z: number, sx: number, sy: number, sz: number) {
  const stone = new THREE.Mesh(slab, material);
  stone.position.set(x, y, z);
  stone.scale.set(sx, sy, sz);
  stone.rotation.set((scatter(seed) - 0.5) * 0.45, scatter(seed + 16) * Math.PI, (scatter(seed + 38) - 0.5) * 0.55);
  parent.add(stone);
  return stone;
}

// The room has local coordinates so future furnishings can be placed on its floor.
function buildRoom(scene: THREE.Scene) {
  const room = new THREE.Group();
  room.name = 'Lookout';
  room.position.y = floorY;
  scene.add(room);

  const stone = slateSurface({ wall: true });
  const floorStone = slateSurface({ floor: true, wall: true, tint: '#cdd2d4' });
  const solidRock = slateSurface({ tint: '#b2b9bd' });
  const timber = weatheredWood();
  const iron = new THREE.MeshStandardMaterial({ color: '#272728', metalness: 0.52, roughness: 0.65 });

  function surface(kind: 'floor' | 'roof' | 'left' | 'right' | 'back', seed: number) {
    const shape = new THREE.PlaneGeometry(1, 1, 20, 14);
    const position = shape.attributes.position;
    const colors: number[] = [];
    const shade = new THREE.Color();
    const base = new THREE.Color(kind === 'floor' ? '#d3d2cc' : '#d0ceca');
    for (let i = 0; i < position.count; i++) {
      const u = position.getX(i) + 0.5;
      const v = position.getY(i) + 0.5;
      const jitter = scatter(i + seed) - 0.5;
      const strata = Math.sin(v * 42 + u * 2.2) * 0.10 + Math.sin(u * 10 + v * 9) * 0.11;
      const x = (u - 0.5) * 8.6;
      const z = v * 8.3 - 0.2;
      switch (kind) {
        case 'floor': position.setXYZ(i, x, jitter * 0.13, z); break;
        case 'roof': position.setXYZ(i, x, 3.35 + jitter * 0.27 + Math.sin(u * 7) * 0.22, z); break;
        case 'left': position.setXYZ(i, -3.91 + strata + jitter * 0.35, v * 3.65 - 0.14, u * 8.3 - 0.2); break;
        case 'right': position.setXYZ(i, 3.92 + strata + jitter * 0.35, v * 3.65 - 0.14, u * 8.3 - 0.2); break;
        case 'back': position.setXYZ(i, x, v * 3.65 - 0.14, 7.9 + jitter * 0.24); break;
      }
      const towardOpening = 1 - v;
      shade.copy(base).multiplyScalar(0.70 + towardOpening * 0.22 + jitter * 0.14 + Math.sin(v * 39 + u) * 0.08);
      colors.push(shade.r, shade.g, shade.b);
    }
    shape.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    shape.computeVertexNormals();
    const mesh = new THREE.Mesh(shape, kind === 'floor' ? floorStone : stone);
    room.add(mesh);
    return mesh;
  }

  const floor = surface('floor', 11);
  const blockers: THREE.Object3D[] = [
    floor, surface('roof', 335), surface('left', 630), surface('right', 921), surface('back', 182),
  ];
  const sill: THREE.Object3D[] = [floor];
  for (let i = 0; i < 14; i++) {
    const x = -4.4 + i * 0.67;
    const lipRock = rock(room, solidRock, i, x, -0.29, -0.15 - scatter(i + 12) * 0.13, 0.66, 0.28 + scatter(i + 311) * 0.24, 0.49);
    sill.push(lipRock);
    blockers.push(lipRock);
    blockers.push(rock(room, solidRock, i + 20, x, 3.48 + Math.sin(i * 1.74) * 0.12, -0.24, 0.71, 0.30 + scatter(i + 221) * 0.34, 0.62));
  }
  for (const side of [-1, 1]) {
    for (let i = 0; i < 6; i++) {
      blockers.push(rock(room, solidRock, i + side * 20, side * 4, 0.35 + i * 0.55, -0.29, 0.54, 0.63, 0.7));
    }
  }

  const bench = new THREE.Group();
  bench.position.set(-2.85, 0, 1.05);
  room.add(bench);
  for (let i = 0; i < 3; i++) {
    blockers.push(box(bench, 0.24, 0.095, 1.57, i * 0.25 - 0.25, 0.69, 0, timber));
  }
  for (const x of [-0.28, 0.28]) {
    for (const z of [-0.63, 0.63]) box(bench, 0.115, 0.65, 0.12, x, 0.32, z, timber);
  }
  const woolCanvas = document.createElement('canvas');
  woolCanvas.width = woolCanvas.height = 96;
  const woolContext = woolCanvas.getContext('2d');
  const blanket = new THREE.MeshStandardMaterial({ color: '#89796a', roughness: 0.98 });
  if (woolContext) {
    const weave = woolContext.createImageData(96, 96);
    for (let y = 0; y < 96; y++) {
      for (let x = 0; x < 96; x++) {
        const pixel = (y * 96 + x) * 4;
        const thread = 172 + ((x + Math.floor(y / 2)) % 2) * 31 + scatter(pixel + 17) * 24;
        const edgeStripe = (x >= 16 && x <= 20) || (x >= 74 && x <= 78);
        weave.data.set(edgeStripe ? [thread * 0.72, thread * 0.54, thread * 0.48, 255] : [thread, thread, thread, 255], pixel);
      }
    }
    woolContext.putImageData(weave, 0, 0);
    blanket.map = new THREE.CanvasTexture(woolCanvas);
    blanket.map.colorSpace = THREE.SRGBColorSpace;
  }
  for (const [index, y] of [0.779, 0.858, 0.928].entries()) {
    const fold = new THREE.Mesh(new RoundedBoxGeometry(0.64 - 0.035 * index, 0.10, 0.46 - 0.028 * index, 3, 0.038), blanket);
    fold.position.set(0.02 - index * 0.016, y, 0.26 + index * 0.025);
    fold.rotation.y = (index - 1) * 0.067;
    bench.add(fold);
  }
  const lamp = new THREE.Group();
  lamp.position.set(-3.56, 1.87, 0.58);
  room.add(lamp);
  const brass = new THREE.MeshStandardMaterial({ color: '#75604b', metalness: 0.6, roughness: 0.39 });
  const glass = new THREE.MeshPhysicalMaterial({
    color: '#efbc85', roughness: 0.22, metalness: 0.09, transparent: true, opacity: 0.19, depthWrite: false,
  });
  function lampPart(radiusTop: number, radiusBottom: number, height: number, y: number, material: THREE.Material) {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radiusTop, radiusBottom, height, 16), material);
    mesh.position.y = y;
    lamp.add(mesh);
  }
  box(lamp, 0.09, 0.31, 0.28, -0.20, 0.17, 0, iron);
  box(lamp, 0.21, 0.042, 0.065, -0.124, 0.32, 0, iron);
  lampPart(0.124, 0.143, 0.13, -0.21, iron);
  lampPart(0.11, 0.135, 0.028, -0.132, brass);
  lampPart(0.116, 0.114, 0.30, 0.022, glass);
  lampPart(0.09, 0.135, 0.085, 0.204, iron);
  lampPart(0.05, 0.075, 0.056, 0.266, brass);
  for (let index = 0; index < 4; index++) {
    const angle = (index + 0.5) * Math.PI / 2;
    box(lamp, 0.014, 0.333, 0.014, Math.sin(angle) * 0.124, 0.025, Math.cos(angle) * 0.124, iron);
  }
  const flame = new THREE.Mesh(new THREE.SphereGeometry(0.039, 9, 7), new THREE.MeshBasicMaterial({
    color: '#ffe1a1', toneMapped: false,
  }));
  flame.position.y = -0.022;
  flame.scale.y = 1.87;
  lamp.add(flame);

  const haloCanvas = document.createElement('canvas');
  haloCanvas.width = haloCanvas.height = 64;
  const haloContext = haloCanvas.getContext('2d');
  if (haloContext) {
    const haloGradient = haloContext.createRadialGradient(32, 32, 1, 32, 32, 32);
    haloGradient.addColorStop(0, '#ffd28b99');
    haloGradient.addColorStop(0.27, '#ff99333c');
    haloGradient.addColorStop(1, '#fd752000');
    haloContext.fillStyle = haloGradient;
    haloContext.fillRect(0, 0, 64, 64);
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(haloCanvas), depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
    }));
    halo.scale.set(0.96, 0.96, 1);
    halo.position.copy(flame.position);
    lamp.add(halo);
  }

  const glow = new THREE.PointLight('#ffad61', 18, 12, 2);
  glow.position.set(0.064, -0.012, 0);
  lamp.add(glow);
  const fill = new THREE.PointLight('#c58a5c', 4.5, 8, 2);
  fill.position.set(-1.7, 1.25, 1.9);
  room.add(fill);
  const moonSpill = new THREE.PointLight('#8eafcf', 4.9, 8.0, 2);
  moonSpill.position.set(2.75, 2.3, 0.74);
  room.add(moonSpill);
  const reflectedLamplight = new THREE.PointLight('#b8aa98', 2.65, 4.5, 2);
  reflectedLamplight.position.set(0.18, 1.86, 4.95);
  room.add(reflectedLamplight);
  for (const surface of blockers) {
    surface.receiveShadow = true;
    surface.castShadow = surface !== floor;
  }
  bench.traverse(object => {
    if (object instanceof THREE.Mesh) {
      object.castShadow = true;
      object.receiveShadow = true;
    }
  });

  return { blockers, sill, glow, room: { group: room, floor, fixtures: [bench] } };
}

function buildCliff(scene: THREE.Scene) {
  const ledges = new THREE.Group();
  scene.add(ledges);
  const materials = ['#9ca9b0', '#a5afb4', '#85939e'].map(tint => slateSurface({ tint }));
  const cliffBlockers: THREE.Object3D[] = [];
  for (let row = 0; row < 7; row++) {
    for (let col = 0; col < 18; col++) {
      const i = row * 18 + col;
      const x = (col - 8.5) * 2.8 + (row % 2) * 0.9;
      const y = row * 3.0 - 1.5 - (row === 6 ? 0.38 : 0);
      const z = -10 + row * 1.26 + scatter(i + 77) * 1.15 + Math.min(Math.abs(x) * 0.14, 3);
      cliffBlockers.push(rock(ledges, materials[i % 3], i + 111, x, y, z, 2.0 + scatter(i + 88) * 1.15, row === 6 ? 1.49 : 2.15, 2.4));
    }
  }
  for (const side of [-1, 1]) {
    for (let i = 0; i < climbShelves.length - 1; i++) {
      const [x, y, z] = climbShelves[i];
      const [nextX, nextY, nextZ] = climbShelves[i + 1];
      for (const t of [0, 0.5]) {
        const centerX = side * THREE.MathUtils.lerp(x, nextX, t);
        const surfaceY = THREE.MathUtils.lerp(y, nextY, t);
        const centerZ = THREE.MathUtils.lerp(z, nextZ, t);
        const seed = 300 + i * 3 + side + t * 2;
        cliffBlockers.push(rock(ledges, materials[(i + 1) % 3], seed,
          centerX, surfaceY - (centerZ > -3.1 ? 1.42 : 1.0), centerZ + 0.38, 1.11 + scatter(seed) * 0.21, 1.24, 1.19));
      }
    }
  }
  const distant = new THREE.Group();
  const distantStone = slateSurface({ tint: '#768491' });
  for (let i = 0; i < 9; i++) {
    const x = -105 + i * 6.4;
    const top = 24 + Math.sin(i * 0.54 + 0.3) * 8 - i * 0.85;
    rock(distant, distantStone, 773 + i, x, top * 0.48, -147 + i * 0.8, 8.8, top * 0.62, 9.3);
  }
  ledges.add(distant);
  distant.updateWorldMatrix(true, true);
  const facade = distant.children.slice();
  const shadowed = new THREE.MeshBasicMaterial({ color: '#191718' });
  const lamplight = new THREE.MeshBasicMaterial({ color: '#d3945b' });
  const survey = new THREE.Raycaster();
  for (const [x, y, width] of [[-93, 18.0, 2.4], [-86, 18.7, 1.65], [-81, 23.1, 2.55], [-73, 15.7, 2.1], [-61, 14.9, 1.45]]) {
    survey.set(new THREE.Vector3(x, y, 0), new THREE.Vector3(0, 0, -1));
    const cut = survey.intersectObjects(facade, false)[0];
    if (!cut) continue;
    const z = cut.point.z + 0.095;
    box(distant, width, 0.54, 0.14, x, y, z, shadowed);
    for (const offset of [-0.29, 0, 0.29]) {
      box(distant, width * 0.23, 0.34, 0.06, x + width * offset, y + 0.035, z + 0.09, lamplight);
    }
  }
  return cliffBlockers;
}

function buildSky(scene: THREE.Scene) {
  const sky = new THREE.Mesh(new THREE.SphereGeometry(325, 40, 24), new THREE.ShaderMaterial({
    uniforms: { horizon: { value: horizonTexture } },
    side: THREE.BackSide,
    depthWrite: false,
    toneMapped: false,
    vertexShader: 'varying vec3 direction; void main() { direction = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader: `
      uniform sampler2D horizon;
      varying vec3 direction;
      void main() {
        vec3 ray = normalize(direction);
        float azimuth = atan(ray.x, -ray.z);
        float altitude = asin(ray.y);
        float skyV = altitude < 0.08 ? 0.20 + (altitude - 0.015) * 4.15 : 0.47 + (altitude - 0.08) / 0.58;
        vec2 uv = vec2(0.49 + azimuth / 1.8, skyV);
        float frame = smoothstep(0.0, 0.12, uv.x) * smoothstep(0.0, 0.12, 1.0 - uv.x)
          * smoothstep(0.0, 0.19, uv.y) * smoothstep(0.0, 0.17, 1.0 - uv.y);
        vec3 ink = mix(vec3(0.037, 0.061, 0.085), vec3(0.007, 0.012, 0.023), smoothstep(-0.13, 0.5, altitude));
        vec3 matte = texture2D(horizon, clamp(uv, 0.0, 1.0)).rgb;
        gl_FragColor = vec4(mix(ink, matte, frame), 1.0);
        #include <colorspace_fragment>
      }
    `,
  }));
  sky.position.copy(lookoutPosition);
  sky.renderOrder = -1;
  scene.add(sky);
}

function buildLowMist(scene: THREE.Scene) {
  const time = { value: 0 };
  const geometry = new THREE.PlaneGeometry(136, 112).rotateX(-Math.PI / 2);
  for (const [index, height] of [1.25, 2.62, 4.1, 6.4].entries()) {
    const sheet = new THREE.Mesh(geometry, new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: { time, layer: { value: index } },
      vertexShader: `
        varying vec2 fogUV;
        void main() {
          fogUV = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec2 fogUV;
        uniform float time;
        uniform float layer;

        float hash(vec2 p) {
          return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
        }

        float noise(vec2 p) {
          vec2 cell = floor(p);
          vec2 f = fract(p);
          f = f * f * (3.0 - 2.0 * f);
          return mix(
            mix(hash(cell), hash(cell + vec2(1.0, 0.0)), f.x),
            mix(hash(cell + vec2(0.0, 1.0)), hash(cell + vec2(1.0, 1.0)), f.x),
            f.y
          );
        }

        void main() {
          vec2 p = fogUV * vec2(6.5, 12.0) + vec2(time * (0.047 + layer * 0.018), -time * 0.022 + layer * 4.3);
          float density = smoothstep(0.45, 1.0, noise(p) + 0.27 * noise(p * 2.31));
          vec2 edge = smoothstep(vec2(0.0), vec2(0.22), fogUV)
            * smoothstep(vec2(0.0), vec2(0.22), 1.0 - fogUV);
          gl_FragColor = vec4(0.34, 0.43, 0.53, density * edge.x * edge.y * (0.16 - layer * 0.023));
        }
      `,
    }));
    sheet.position.set(index * 6 - 8, height, -69 - index * 11);
    scene.add(sheet);
  }
  return time;
}

export function buildLookout(scene: THREE.Scene) {
  scene.fog = new THREE.FogExp2('#253949', 0.0071);
  buildSky(scene);
  const mistTime = buildLowMist(scene);
  const terrain = buildTerrain(scene);
  const { trunks, trees } = buildForest(scene);
  const cliff = buildCliff(scene);
  const { blockers, sill, glow, room } = buildRoom(scene);
  scene.updateMatrixWorld(true);

  scene.add(new THREE.HemisphereLight('#adc6de', '#3b4044', 0.90));
  const moon = new THREE.DirectionalLight('#b9d5f4', 1.9);
  moon.position.set(23, floorY + 15, -43);
  moon.target.position.set(0, floorY + 0.8, 2.2);
  moon.castShadow = true;
  moon.shadow.mapSize.set(1024, 1024);
  moon.shadow.camera.left = moon.shadow.camera.bottom = -7.5;
  moon.shadow.camera.right = moon.shadow.camera.top = 7.5;
  moon.shadow.camera.near = 34;
  moon.shadow.camera.far = 65;
  moon.shadow.bias = -0.0001;
  moon.shadow.normalBias = 0.055;
  moon.shadow.radius = 0.85;
  moon.shadow.autoUpdate = false;
  moon.shadow.needsUpdate = true;
  scene.add(moon, moon.target);

  return {
    blockers: [terrain, trunks, ...blockers, ...cliff],
    cliff, sill, trees,
    glow, room, mistTime, moon,
  };
}
