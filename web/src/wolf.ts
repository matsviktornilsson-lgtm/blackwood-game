import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { scatter } from './geometry';
import guardHair from './assets/werewolf/guard-hair.webp';
import shortHair from './assets/werewolf/short-hair.webp';
import hideTexture from './assets/werewolf/hide.webp';
import underfur from './assets/werewolf/underfur.webp';
import { reach, roundLimbJoints, skinLimb } from './wolf-rig';
import { createWolfBreath } from './wolf-breath';
import { braceOnRock, type ClimbPose } from './wolf-climb';
import { createPawTrack, initializePaw, poseHindLeg, prepareHindLeg, settlePaw, stepPaw, supportHeight } from './wolf-gait';

const textureLoader = new THREE.TextureLoader();

function hideMaterial(url: string, color: string, bumpScale: number, roughness = 0.91) {
  const map = textureLoader.load(url);
  map.colorSpace = THREE.SRGBColorSpace;
  map.wrapS = map.wrapT = THREE.RepeatWrapping;
  map.anisotropy = 4;
  const relief = map.clone();
  relief.colorSpace = THREE.NoColorSpace;
  return new THREE.MeshStandardMaterial({ color, map, bumpMap: relief, bumpScale, roughness });
}

const coat = hideMaterial(guardHair, '#d2cdc7', 0.009);
const limbCoat = coat.clone();
limbCoat.vertexColors = true;
limbCoat.bumpScale = 0.0065;
const face = hideMaterial(shortHair, '#bdb8af', 0.004);
const facePelt = face.clone();
facePelt.vertexColors = true;
const torsoPelt = hideMaterial(underfur, '#bfbcb5', 0.0058);
torsoPelt.vertexColors = true;
const sparse = hideMaterial(hideTexture, '#968a83', 0.004, 0.78);
const nose = hideMaterial(hideTexture, '#80746e', 0.002, 0.4);
const earSkin = hideMaterial(hideTexture, '#78635e', 0.003, 0.87);
const cavity = new THREE.MeshStandardMaterial({ color: '#100c0c', roughness: 0.77 });
const gums = new THREE.MeshStandardMaterial({ color: '#392022', roughness: 0.54, metalness: 0.02 });
const tongueSurface = new THREE.MeshPhysicalMaterial({ color: '#4a2c32', roughness: 0.47, clearcoat: 0.54, clearcoatRoughness: 0.32 });
const mouthFoldMaterial = new THREE.MeshStandardMaterial({ color: '#29191a', roughness: 0.61, side: THREE.DoubleSide });
const lipSurface = hideMaterial(hideTexture, '#4d3e3c', 0.0024, 0.57);
const enamel = new THREE.MeshStandardMaterial({ color: '#b7a68a', roughness: 0.48 });
const stainedEnamel = new THREE.MeshStandardMaterial({ color: '#9a866f', roughness: 0.61 });
const claw = new THREE.MeshStandardMaterial({ color: '#393530', roughness: 0.60 });
const iris = new THREE.MeshStandardMaterial({ color: '#987345', emissive: '#886139', emissiveIntensity: 0.075, roughness: 0.25 });
const pupil = new THREE.MeshStandardMaterial({ color: '#070606', roughness: 0.29 });
const glint = new THREE.MeshStandardMaterial({ color: '#ada196', emissive: '#ab997e', emissiveIntensity: 0.36, roughness: 0.28 });
const hull = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide });
const oval = new THREE.SphereGeometry(1, 16, 12);
const torsoBounds = new THREE.CapsuleGeometry(0.40, 0.86, 4, 8);
const headBounds = new THREE.SphereGeometry(1, 10, 8);

type Point = readonly [x: number, y: number, z: number];
type Section = readonly [x: number, y: number, z: number, width: number, depth: number];
type Profile = readonly [z: number, y: number, width: number, height: number];
type LimbShape = { kind: 'arm' | 'leg'; side: number };

function mesh(parent: THREE.Object3D, material: THREE.Material, geometry: THREE.BufferGeometry) {
  const part = new THREE.Mesh(geometry, material);
  parent.add(part);
  return part;
}

function ellipsoid(parent: THREE.Object3D, material: THREE.Material, position: Point, scale: Point) {
  const part = mesh(parent, material, oval);
  part.position.set(...position);
  part.scale.set(...scale);
  return part;
}

function joint(parent: THREE.Object3D, position: Point) {
  const group = new THREE.Group();
  group.position.set(...position);
  parent.add(group);
  return group;
}

function sweep(sections: readonly Section[], sides: number, limb?: LimbShape) {
  if (sides >= 14 && sections.length >= 4) {
    const centers = new THREE.CatmullRomCurve3(sections.map(([x, y, z]) => new THREE.Vector3(x, y, z)), false, 'catmullrom', 0.45);
    const radii = new THREE.CatmullRomCurve3(sections.map(([, , , width, depth], i) => new THREE.Vector3(width, depth, i)), false, 'catmullrom', 0.45);
    const rings = (sections.length - 1) * (limb ? 5 : 3);
    sections = Array.from({ length: rings + 1 }, (_, i) => {
      const t = i / rings;
      const center = centers.getPoint(t);
      const radius = radii.getPoint(t);
      return [center.x, center.y, center.z, Math.max(0.001, radius.x), Math.max(0.001, radius.y)] as const;
    });
  }
  const path = sections.map(([x, y, z]) => new THREE.Vector3(x, y, z));
  const points: number[] = [];
  const uv: number[] = [];
  const along: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const direction = new THREE.Vector3();
  const across = new THREE.Vector3();
  const around = new THREE.Vector3();
  let distance = 0;

  for (const [ring, center] of path.entries()) {
    const previous = path[Math.max(0, ring - 1)];
    const next = path[Math.min(path.length - 1, ring + 1)];
    direction.subVectors(next, previous).normalize();
    across.set(1, 0, 0);
    if (Math.abs(direction.x) > 0.94) across.set(0, 0, 1);
    across.addScaledVector(direction, -across.dot(direction)).normalize();
    around.crossVectors(direction, across);
    distance += center.distanceTo(previous);
    const [, , , width, depth] = sections[ring];
    const upper = limb ? Math.exp(-((center.y + 0.13) ** 2) / 0.043) : 0;
    const lower = limb ? Math.exp(-((center.y + (limb.kind === 'arm' ? 0.66 : 0.54)) ** 2) / 0.027) : 0;
    for (let side = 0; side <= sides; side++) {
      const angle = (side % sides) / sides * Math.PI * 2;
      const cosine = Math.cos(angle);
      const sine = Math.sin(angle);
      const outside = cosine * (limb?.side ?? 1);
      const shape = 1 + upper * (0.105 * outside - 0.072 * sine + 0.095 * Math.cos(2 * angle + distance * 3))
        + lower * (0.065 * outside + 0.095 * Math.cos(2 * angle - distance * 4));
      const cross = cosine * width * shape;
      const thickness = sine * depth * shape;
      points.push(
        center.x + across.x * cross + around.x * thickness,
        center.y + across.y * cross + around.y * thickness,
        center.z + across.z * cross + around.z * thickness,
      );
      uv.push(side / sides + (limb ? Math.sin(distance * 2.5) * 0.085 : 0), 0.91 - distance * 1.13);
      if (limb) {
        along.push(center.y);
        const coatFade = THREE.MathUtils.smoothstep(-center.y, limb.kind === 'arm' ? 0.83 : 0.70, 1.20);
        const tone = 0.79 + 0.16 * outside + 0.06 * sine + 0.044 * Math.sin(distance * 11 + 3 * angle);
        colors.push(tone + coatFade * 0.12, tone + coatFade * 0.07, tone + coatFade * 0.04);
      }
      if (ring === 0 || side === 0) continue;
      const a = (ring - 1) * (sides + 1) + side - 1;
      const b = a + sides + 1;
      indices.push(a, a + 1, b + 1, a, b + 1, b);
    }
  }

  for (const ring of [0, path.length - 1]) {
    const center = path[ring];
    const cap = points.length / 3;
    const rim = ring * (sides + 1);
    points.push(center.x, center.y, center.z);
    uv.push(0.5, uv[rim * 2 + 1]);
    if (limb) {
      along.push(center.y);
      colors.push(0.81, 0.79, 0.76);
    }
    for (let side = 0; side < sides; side++) {
      if (ring === 0) indices.push(cap, rim + side + 1, rim + side);
      else indices.push(cap, rim + side, rim + side + 1);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  if (limb) {
    geometry.setAttribute('limbY', new THREE.Float32BufferAttribute(along, 1));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  }
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  const normals = geometry.attributes.normal;
  for (let ring = 0; ring < path.length; ring++) {
    const a = ring * (sides + 1);
    const b = a + sides;
    const smooth = direction.fromBufferAttribute(normals, a).add(across.fromBufferAttribute(normals, b)).normalize();
    normals.setXYZ(a, smooth.x, smooth.y, smooth.z);
    normals.setXYZ(b, smooth.x, smooth.y, smooth.z);
  }
  return geometry;
}

function form(parent: THREE.Object3D, material: THREE.Material, sections: readonly Section[], sides = 20) {
  return mesh(parent, material, sweep(sections, sides));
}

function profile(parent: THREE.Object3D, material: THREE.Material, sections: readonly Profile[]) {
  return form(parent, material, sections.map(([z, y, width, height]) => [0, y, z, width, height] as const), 24);
}

function tintPelt(surface: THREE.Mesh<THREE.BufferGeometry>, muzzle: boolean) {
  const { position, normal } = surface.geometry.attributes;
  const colors = new Float32Array(position.count * 3);
  for (let i = 0; i < position.count; i++) {
    const x = position.getX(i);
    const y = position.getY(i);
    const z = position.getZ(i);
    const ash = 0.10 * Math.sin(x * 28 + z * 17 + y * 14) + 0.047 * Math.sin(y * 44 - x * 33 + z * 24);
    const back = THREE.MathUtils.smoothstep(normal.getY(i), -0.40, 0.85);
    const bridge = muzzle ? THREE.MathUtils.smoothstep(-z, 0.11, 0.45) : 0;
    const darkMask = muzzle ? 0.17 * bridge + 0.11 * back : 0;
    const gray = 0.71 + (muzzle ? 0.12 : 0.30) * back + ash - darkMask;
    const silver = muzzle ? 0.08 * Math.abs(normal.getX(i)) : 0.09 * back;
    colors.set([gray + 0.042, gray + 0.018 + silver * 0.40, gray + silver], i * 3);
  }
  surface.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
}

function batch(group: THREE.Object3D) {
  const clusters = new Map<THREE.Material, THREE.Mesh<THREE.BufferGeometry, THREE.Material>[]>();
  for (const part of group.children) {
    if (!(part instanceof THREE.Mesh) || part.children.length || Array.isArray(part.material)) continue;
    const parts = clusters.get(part.material) ?? [];
    parts.push(part);
    clusters.set(part.material, parts);
  }
  for (const [material, parts] of clusters) {
    if (parts.length < 2) continue;
    const copies = parts.map(part => {
      part.updateMatrix();
      const shape = part.geometry.index ? part.geometry.toNonIndexed() : part.geometry.clone();
      shape.applyMatrix4(part.matrix);
      return shape;
    });
    const merged = mergeGeometries(copies);
    copies.forEach(shape => shape.dispose());
    if (merged) {
      group.remove(...parts);
      mesh(group, material, merged);
    }
  }
}

const guardFur = new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, roughness: 0.93 });
const groomCache = new Map<'cheek' | 'mantle' | 'tail', THREE.BufferGeometry>();

function growFur(surface: THREE.BufferGeometry, region: 'cheek' | 'mantle' | 'tail' | LimbShape, ringSize: number) {
  const cheek = region === 'cheek';
  const tail = region === 'tail';
  const limb = typeof region === 'object' ? region : undefined;
  const { position, normal, limbY } = surface.attributes;
  const along: number[] = [];
  const points: number[] = [];
  const normals: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const base = new THREE.Vector3();
  const outward = new THREE.Vector3();
  const flow = new THREE.Vector3();
  const cross = new THREE.Vector3();
  const root = new THREE.Vector3();
  const middle = new THREE.Vector3();
  const tip = new THREE.Vector3();

  for (let i = 0; i < position.count - 2; i++) {
    if (i % ringSize === ringSize - 1 || scatter(i * 17) > (limb ? 0.24 : tail ? 0.38 : cheek ? 0.72 : 0.69)) continue;
    base.fromBufferAttribute(position, i);
    outward.fromBufferAttribute(normal, i);
    const cheekFur = base.z > -0.147 && Math.abs(base.x) > 0.105 && base.y < 0.166;
    const mantleFur = base.z < 0.43 && (outward.y > 0.22 || Math.abs(outward.x) > 0.69);
    const limbFur = limb && base.y < 0.17 && base.y > -0.96 && (outward.x * limb.side > 0.06 || outward.z > 0.20);
    if (!(limb ? limbFur : tail ? base.y > -0.37 : cheek ? cheekFur : mantleFur)) continue;
    const clump = scatter(i + 43);
    for (let hair = 0; hair < (limb ? 3 : tail ? 4 : 9); hair++) {
      const seed = i * 131 + hair * 13;
      const loft = limb ? THREE.MathUtils.smoothstep(base.y, -0.98, -0.07) : 1;
      const strand = 0.32 + scatter(seed) ** 1.4 * 0.93;
      const length = limb ? 0.012 + loft * (0.033 + clump * 0.036) * strand
        : tail ? (0.017 + clump * 0.048) * strand
        : (cheek ? 0.032 : 0.049) + clump * (cheek ? 0.081 : 0.142) * strand;
      const width = limb ? 0.00065 + scatter(seed + 1) * 0.0013 : 0.0010 + scatter(seed + 1) * 0.0019;
      flow.set((scatter(seed + 2) - 0.5) * 0.82, limb || tail ? -0.92 : cheek ? -0.82 : -0.31, limb ? 0.30 : 0.83);
      flow.addScaledVector(outward, -flow.dot(outward)).normalize();
      cross.crossVectors(flow, outward).normalize();
      root.copy(base).addScaledVector(outward, limb ? -0.004 : -0.010)
        .addScaledVector(cross, (scatter(seed + 3) - 0.5) * (limb ? 0.028 : 0.057))
        .addScaledVector(flow, (scatter(seed + 4) - 0.5) * (limb ? 0.016 : 0.035));
      middle.copy(root).addScaledVector(flow, length * 0.42).addScaledVector(outward, length * 0.33);
      tip.copy(root).addScaledVector(flow, length).addScaledVector(outward, length * (0.13 + scatter(seed + 5) * 0.27));
      cross.applyAxisAngle(flow, scatter(seed + 6) * Math.PI);
      const shade = 0.014 + scatter(seed + 7) ** 2.6 * 0.088;
      const start = points.length / 3;
      if (limb) {
        const y = limbY.getX(i);
        along.push(y, y, y, y, y);
      }
      for (const [center, span, light] of [[root, 0.68, 0.54], [middle, 1, 0.9]] as const) {
        for (const side of [-1, 1]) {
          const offset = side * width * span;
          points.push(center.x + cross.x * offset, center.y + cross.y * offset, center.z + cross.z * offset);
          normals.push(outward.x, outward.y, outward.z);
          colors.push(shade * light, shade * light * 0.86, shade * light * 0.73);
        }
      }
      points.push(tip.x, tip.y, tip.z);
      normals.push(outward.x, outward.y, outward.z);
      const tipShade = shade * 1.2;
      colors.push(tipShade, tipShade * 0.86, tipShade * 0.73);
      indices.push(start, start + 1, start + 2, start + 1, start + 3, start + 2, start + 2, start + 3, start + 4);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geometry.setIndex(indices);
  if (limb) geometry.setAttribute('limbY', new THREE.Float32BufferAttribute(along, 1));
  return geometry;
}

function groom(surface: THREE.Mesh<THREE.BufferGeometry>, region: 'cheek' | 'mantle' | 'tail', ringSize = 25) {
  let fur = groomCache.get(region);
  if (!fur) {
    fur = growFur(surface.geometry, region, ringSize);
    groomCache.set(region, fur);
  }
  mesh(surface, guardFur, fur);
}

const limbSurfaces = new Map<string, { skin: THREE.BufferGeometry; fur: THREE.BufferGeometry }>();

function sculptLimb(sections: readonly Section[], kind: LimbShape['kind'], side: number) {
  const key = kind + side;
  let surface = limbSurfaces.get(key);
  if (!surface) {
    const shape = { kind, side };
    const skin = sweep(sections, 38, shape);
    surface = { skin, fur: growFur(skin, shape, 39) };
    limbSurfaces.set(key, surface);
  }
  return surface;
}

function shapeEar(head: THREE.Group, side: number) {
  const ear = joint(head, [side * 0.147, 0.121, 0.074]);
  const tip = side < 0 ? 0.213 : 0.178;
  form(ear, coat, [
    [0, -0.018, 0, 0.064, 0.046], [side * 0.023, 0.068, 0.019, 0.064, 0.035],
    [side * 0.046, 0.138, 0.058, 0.038, 0.022], [side * 0.071, tip - 0.024, 0.083, 0.016, 0.012],
    [side * 0.086, tip - 0.009, 0.101, 0.008, 0.006], [side * 0.093, tip, 0.107, 0.002, 0.002],
  ], 16);
  form(ear, earSkin, [
    [side * 0.012, 0.018, -0.033, 0.032, 0.015], [side * 0.026, 0.079, -0.016, 0.045, 0.012],
    [side * 0.045, 0.129, 0.026, 0.027, 0.009], [side * 0.070, tip - 0.034, 0.073, 0.005, 0.003],
  ], 14);
  return ear;
}

function shapeMouthFolds(head: THREE.Group, jaw: THREE.Group) {
  const rows = 7;
  const columns = 5;
  const indices: number[] = [];
  for (let row = 0; row < rows; row++) {
    for (let column = 0; column < columns; column++) {
      const a = row * (columns + 1) + column;
      const b = a + columns + 1;
      indices.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  const folds = [-1, 1].map(side => {
    const geometry = new THREE.BufferGeometry();
    const points = new THREE.Float32BufferAttribute(new Float32Array((rows + 1) * (columns + 1) * 3), 3);
    geometry.setAttribute('position', points);
    geometry.setIndex(indices);
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(side * 0.11, -0.13, -0.16), 0.35);
    mesh(head, mouthFoldMaterial, geometry);
    return { side, geometry, points };
  });
  const upper = new THREE.Vector3();
  const lower = new THREE.Vector3();
  const crease = new THREE.Vector3();
  const pose = () => {
    for (const { side, geometry, points } of folds) {
      for (let row = 0; row <= rows; row++) {
        const along = row / rows;
        upper.set(side * (0.155 - along * 0.052), -0.106 + along * 0.010, -0.061 - along * 0.227);
        lower.set(side * (0.139 - along * 0.057), -0.052 + along * 0.028, -0.095 - along * 0.235)
          .applyQuaternion(jaw.quaternion).add(jaw.position);
        for (let column = 0; column <= columns; column++) {
          const stretch = column / columns;
          const middle = Math.sin(stretch * Math.PI);
          crease.lerpVectors(upper, lower, stretch);
          crease.x -= side * middle * (0.014 + along * 0.011);
          crease.z += middle * along ** 2 * 0.063;
          points.setXYZ(row * (columns + 1) + column, crease.x, crease.y, crease.z);
        }
      }
      points.needsUpdate = true;
      geometry.computeVertexNormals();
    }
  };
  pose();
  return pose;
}

function shapeHead(chest: THREE.Group) {
  const head = joint(chest, [0, 0.575, -0.844]);
  const skull = profile(head, facePelt, [
    [0.244, 0.024, 0.112, 0.113], [0.193, 0.046, 0.179, 0.153],
    [0.095, 0.059, 0.226, 0.167], [0.011, 0.053, 0.234, 0.153],
    [-0.078, 0.044, 0.210, 0.133], [-0.152, 0.017, 0.162, 0.111],
    [-0.220, -0.007, 0.132, 0.095], [-0.291, -0.019, 0.114, 0.081],
    [-0.370, -0.030, 0.104, 0.073], [-0.445, -0.038, 0.093, 0.063],
    [-0.483, -0.042, 0.074, 0.044],
  ]);
  tintPelt(skull, true);
  groom(skull, 'cheek');
  profile(head, nose, [
    [-0.440, -0.037, 0.069, 0.039], [-0.469, -0.036, 0.087, 0.048],
    [-0.499, -0.041, 0.078, 0.041], [-0.517, -0.046, 0.057, 0.031], [-0.523, -0.046, 0.028, 0.019],
  ]);
  const jaw = joint(head, [0, -0.083, 0.047]);
  profile(jaw, face, [
    [0.124, -0.035, 0.117, 0.051], [0.064, -0.056, 0.161, 0.073],
    [-0.039, -0.081, 0.144, 0.072], [-0.133, -0.079, 0.112, 0.063],
    [-0.236, -0.061, 0.086, 0.050], [-0.348, -0.046, 0.074, 0.039],
    [-0.457, -0.030, 0.063, 0.027], [-0.513, -0.025, 0.049, 0.021],
    [-0.532, -0.025, 0.025, 0.014],
  ]);
  profile(jaw, gums, [
    [0.005, -0.032, 0.103, 0.026], [-0.115, -0.040, 0.105, 0.024],
    [-0.275, -0.027, 0.080, 0.021], [-0.428, -0.011, 0.062, 0.015],
    [-0.506, -0.006, 0.041, 0.011],
  ]);
  profile(head, cavity, [
    [0.015, -0.092, 0.117, 0.045], [-0.091, -0.113, 0.137, 0.040],
    [-0.211, -0.116, 0.116, 0.026], [-0.332, -0.106, 0.089, 0.019],
    [-0.427, -0.096, 0.075, 0.018], [-0.486, -0.083, 0.052, 0.010],
  ]);

  profile(jaw, tongueSurface, [
    [-0.066, -0.040, 0.047, 0.018], [-0.145, -0.036, 0.052, 0.021],
    [-0.246, -0.022, 0.050, 0.019], [-0.336, -0.011, 0.040, 0.014],
    [-0.400, -0.008, 0.032, 0.012], [-0.439, -0.004, 0.017, 0.008],
    [-0.454, -0.006, 0.004, 0.004],
  ]);
  const eyes: THREE.Group[] = [];
  const lips: THREE.Group[] = [];
  const ears = [-1, 1].map(side => shapeEar(head, side));
  for (const side of [-1, 1]) {
    const nostril = ellipsoid(head, cavity, [side * 0.058, -0.043, -0.501], [0.025, 0.012, 0.011]);
    nostril.rotation.y = side * -0.70;
    const eye = joint(head, [side * 0.132, 0.052, -0.208]);
    eye.rotation.y = side * -0.45;
    eyes.push(eye);
    eye.rotation.z = side * 0.19;
    ellipsoid(eye, cavity, [0, 0, 0], [0.034, 0.022, 0.022]);
    ellipsoid(eye, iris, [0, -0.001, -0.013], [0.018, 0.011, 0.011]);
    ellipsoid(eye, pupil, [0, -0.001, -0.023], [0.009, 0.009, 0.004]);
    ellipsoid(eye, glint, [-0.004, 0.005, -0.027], [0.0028, 0.0024, 0.0012]);
    form(head, face, [
      [side * 0.194, 0.102, -0.069, 0.026, 0.030],
      [side * 0.163, 0.083, -0.154, 0.031, 0.024],
      [side * 0.132, 0.068, -0.219, 0.021, 0.013],
      [side * 0.108, 0.051, -0.262, 0.016, 0.009],
      [side * 0.087, 0.046, -0.287, 0.004, 0.005],
    ], 20);
    const lip = joint(head, [side * 0.150, -0.079, -0.128]);
    lips.push(lip);
    form(lip, lipSurface, [
      [side * 0.007, -0.016, 0.060, 0.021, 0.022],
      [side * 0.001, -0.005, 0.023, 0.019, 0.022],
      [-side * 0.027, -0.001, -0.079, 0.015, 0.018],
      [-side * 0.048, -0.009, -0.177, 0.012, 0.014],
      [-side * 0.056, -0.013, -0.240, 0.011, 0.012],
      [-side * 0.067, -0.010, -0.296, 0.010, 0.011],
      [-side * 0.092, -0.001, -0.345, 0.006, 0.006],
    ], 20);
    const zPositions = [-0.433, -0.382, -0.341, -0.292, -0.248, -0.198, -0.151];
    zPositions.forEach((z, index) => {
      const x = side * (0.064 + index * 0.0104);
      const length = index === 0 ? (side < 0 ? 0.094 : 0.084)
        : 0.022 + scatter(index * 15 + side + 28) * 0.021;
      const upperY = -0.091 - index * 0.004;
      const ivory = index === 0 || index % 3 === 1 ? enamel : stainedEnamel;
      curvedClaw(head, [x, upperY + 0.009, z], [x * 1.03, upperY - length * 0.63, z + length * 0.13],
        [x * 0.91, upperY - length, z + length * 0.36], index === 0 ? 0.018 : 0.011, ivory);
      const lowerY = -0.010 - index * 0.0054;
      const lowerLength = index === 1 ? 0.066 : 0.019 + scatter(index * 18 + 56) * 0.016;
      curvedClaw(jaw, [x * 0.88, lowerY - 0.006, z - 0.041], [x * 0.91, lowerY + lowerLength * 0.62, z - 0.041],
        [x * 0.84, lowerY + lowerLength, z - 0.022], index === 1 ? 0.015 : 0.0095, ivory);
    });
    for (let i = 0; i < 3; i++) {
      const x = side * (0.010 + i * 0.016);
      const z = -0.482 + i * 0.007;
      const length = 0.024 - i * 0.002;
      curvedClaw(head, [x, -0.082, z], [x, -0.094, z + 0.003],
        [x * 0.99, -0.086 - length, z + 0.007], 0.0087, enamel);
    }
  }

  batch(head);
  batch(jaw);
  return { head, jaw, ears, eyes, lips, poseMouthFolds: shapeMouthFolds(head, jaw), poseBreath: createWolfBreath(head) };
}

function curvedClaw(parent: THREE.Object3D, base: Point, middle: Point, tip: Point, width: number, material = claw) {
  form(parent, material, [
    [...base, width, width * 0.76],
    [THREE.MathUtils.lerp(base[0], middle[0], 0.48), THREE.MathUtils.lerp(base[1], middle[1], 0.48),
      THREE.MathUtils.lerp(base[2], middle[2], 0.48), width * 0.81, width * 0.62],
    [...middle, width * 0.52, width * 0.45],
    [...tip, 0.0012, 0.001],
  ], 16);
}

function shapeArm(chest: THREE.Group, side: number) {
  const { skin, fur } = sculptLimb([
    [-side * 0.181, 0.170, 0.110, 0.019, 0.025],
    [-side * 0.128, 0.146, 0.075, 0.105, 0.128],
    [-side * 0.057, 0.105, 0.032, 0.149, 0.168],
    [side * 0.029, 0.026, 0.017, 0.173, 0.165],
    [side * 0.082, -0.105, 0.012, 0.150, 0.153],
    [side * 0.113, -0.235, -0.007, 0.128, 0.142],
    [side * 0.143, -0.361, 0.020, 0.096, 0.108],
    [side * 0.148, -0.465, 0.042, 0.087, 0.092],
    [side * 0.153, -0.542, 0.009, 0.098, 0.102],
    [side * 0.170, -0.654, -0.027, 0.110, 0.108],
    [side * 0.169, -0.764, -0.067, 0.099, 0.091],
    [side * 0.158, -0.901, -0.119, 0.073, 0.071],
    [side * 0.147, -1.026, -0.167, 0.052, 0.059],
    [side * 0.144, -1.099, -0.198, 0.055, 0.053],
    [side * 0.146, -1.165, -0.214, 0.076, 0.049],
    [side * 0.151, -1.219, -0.228, 0.084, 0.042],
    [side * 0.147, -1.252, -0.233, 0.069, 0.032],
    [side * 0.145, -1.267, -0.237, 0.027, 0.020],
  ], 'arm', side);
  const limb = skinLimb(chest, skin, limbCoat, [side * 0.342, 0.507, -0.409],
    [side * 0.144, -0.459, 0.048], [0, -0.641, -0.247], { geometry: fur, material: guardFur });
  const wrist = limb.end;
  for (let i = 0; i < 4; i++) {
    const x = (i - 1.5) * 0.043;
    const length = 0.129 + Math.sin((i + 0.1) / 3 * Math.PI) * 0.045;
    const base = -0.115 + Math.abs(i - 1.5) * 0.014;
    form(wrist, sparse, [
      [x * 0.85, base + 0.045, -0.024, 0.018, 0.020],
      [x, base, -0.036, 0.026, 0.027],
      [x * 1.13, base - length * 0.26, -0.052, 0.020, 0.019],
      [x * 1.20, base - length * 0.47, -0.076, 0.023, 0.021],
      [x * 1.23, base - length * 0.70, -0.101, 0.016, 0.016],
      [x * 1.18, base - length * 0.90, -0.133, 0.014, 0.015],
      [x * 1.15, base - length, -0.149, 0.009, 0.010],
    ], 20);
    curvedClaw(wrist, [x * 1.17, base - length + 0.009, -0.140],
      [x * 1.14, base - length - 0.024, -0.172],
      [x * 1.04, base - length - 0.033, -0.199], 0.012);
  }
  form(wrist, sparse, [
    [-side * 0.039, -0.025, -0.009, 0.022, 0.024],
    [-side * 0.068, -0.056, -0.003, 0.034, 0.031],
    [-side * 0.105, -0.097, -0.021, 0.027, 0.022],
    [-side * 0.116, -0.123, -0.047, 0.018, 0.016],
    [-side * 0.112, -0.148, -0.076, 0.012, 0.011],
  ], 20);
  curvedClaw(wrist, [-side * 0.113, -0.139, -0.071], [-side * 0.112, -0.163, -0.089],
    [-side * 0.105, -0.174, -0.105], 0.010);
  batch(wrist);
  return limb;
}

function shapeLeg(pelvis: THREE.Group, side: number) {
  const { skin, fur } = sculptLimb([
    [-side * 0.116, 0.143, 0.055, 0.020, 0.029],
    [-side * 0.076, 0.092, 0.053, 0.111, 0.146],
    [side * 0.002, 0.043, 0.045, 0.163, 0.176],
    [side * 0.046, -0.066, 0.029, 0.181, 0.193],
    [side * 0.079, -0.171, -0.027, 0.154, 0.168],
    [side * 0.105, -0.274, -0.123, 0.127, 0.135],
    [side * 0.119, -0.388, -0.209, 0.088, 0.100],
    [side * 0.124, -0.452, -0.181, 0.088, 0.101],
    [side * 0.146, -0.530, -0.097, 0.112, 0.105],
    [side * 0.151, -0.625, 0.022, 0.087, 0.086],
    [side * 0.154, -0.716, 0.113, 0.059, 0.072],
    [side * 0.154, -0.778, 0.163, 0.058, 0.065],
    [side * 0.153, -0.834, 0.146, 0.054, 0.058],
    [side * 0.149, -0.914, 0.082, 0.049, 0.046],
    [side * 0.139, -0.991, 0.010, 0.056, 0.047],
    [side * 0.121, -1.032, -0.049, 0.087, 0.044],
    [side * 0.118, -1.051, -0.087, 0.094, 0.032],
    [side * 0.118, -1.055, -0.108, 0.059, 0.018],
  ], 'leg', side);
  const limb = skinLimb(pelvis, skin, limbCoat, [side * 0.229, 0, 0],
    [side * 0.120, -0.400, -0.218], [side * 0.035, -0.379, 0.383], { geometry: fur, material: guardFur });
  const toes = joint(limb.end, [-side * 0.035, -0.265, -0.234]);
  for (let i = 0; i < 4; i++) {
    const x = (i - 1.5) * 0.046;
    const length = 0.102 + Math.sin(i / 3 * Math.PI) * 0.023;
    form(toes, sparse, [
      [x * 0.74, 0.002, 0.030, 0.023, 0.022],
      [x * 0.93, 0.001, -0.014, 0.031, 0.033],
      [x * 1.08, -0.004, -length * 0.52, 0.030, 0.032],
      [x * 1.06, -0.015, -length * 0.83, 0.026, 0.026],
      [x, -0.019, -length, 0.012, 0.013],
    ], 20);
    curvedClaw(toes, [x * 1.01, -0.016, -length * 0.88], [x, -0.024, -length - 0.019],
      [x * 0.97, -0.037, -length - 0.039], 0.012);
  }
  batch(toes);
  return { ...limb, toes };
}

export function createWolf() {
  const root = new THREE.Group();
  root.name = 'Werewolf';
  const chest = joint(root, [0, 1.13, 0.232]);
  const torso = profile(chest, torsoPelt, [
    [0.542, -0.020, 0.150, 0.168], [0.423, 0.037, 0.268, 0.238],
    [0.277, 0.105, 0.262, 0.260], [0.118, 0.173, 0.230, 0.246],
    [-0.022, 0.283, 0.260, 0.286], [-0.160, 0.375, 0.340, 0.346],
    [-0.300, 0.466, 0.402, 0.376], [-0.440, 0.527, 0.385, 0.345],
    [-0.574, 0.563, 0.309, 0.297], [-0.710, 0.568, 0.239, 0.233],
    [-0.833, 0.566, 0.188, 0.181], [-0.913, 0.565, 0.124, 0.132],
  ]);
  tintPelt(torso, false);
  groom(torso, 'mantle');
  const pelvis = joint(root, [0, 1.106, 0.419]);
  const tail = joint(pelvis, [0, -0.016, 0.287]);
  const tailSkin = form(tail, coat, [
    [0, 0.033, -0.053, 0.071, 0.083], [-0.004, -0.028, 0.048, 0.090, 0.083],
    [-0.012, -0.120, 0.164, 0.077, 0.074], [-0.032, -0.225, 0.259, 0.061, 0.067],
    [-0.054, -0.312, 0.308, 0.044, 0.050], [-0.088, -0.389, 0.319, 0.029, 0.036],
    [-0.109, -0.443, 0.304, 0.011, 0.018], [-0.120, -0.470, 0.291, 0.002, 0.004],
  ], 22);
  groom(tailSkin, 'tail', 23);

  const { head, jaw, ears, eyes, lips, poseMouthFolds, poseBreath } = shapeHead(chest);
  const arms = [-1, 1].map(side => shapeArm(chest, side));
  const legs = [-1, 1].map(side => shapeLeg(pelvis, side));

  const torsoHit = mesh(chest, hull, torsoBounds);
  torsoHit.position.set(0, 0.382, -0.202);
  torsoHit.rotation.x = -0.51;
  torsoHit.visible = false;
  const headHit = mesh(head, hull, headBounds);
  headHit.position.set(0, -0.016, -0.187);
  headHit.scale.set(0.213, 0.207, 0.419);
  headHit.visible = false;

  const bodyJoints = [pelvis, chest, head, jaw, tail, ...ears, ...arms.flatMap(limb => [limb.first, limb.middle, limb.end])];
  const joints = [...bodyJoints, ...legs.flatMap(limb => [limb.first, limb.middle, limb.end, limb.toes])];
  const animation = {
    motion: undefined as WolfMotion | undefined,
    phase: 0,
    blend: 1,
    speed: 0,
    supportDrop: 0,
    settling: 1,
    settleFirst: 0,
    falling: false,
    previous: new THREE.Vector3(),
    chestFrom: new THREE.Vector3(),
    pelvisFrom: new THREE.Vector3(),
    bodyJoints,
    joints,
    from: joints.map(() => new THREE.Quaternion()),
    paws: legs.map(createPawTrack),
  };

  const surfaces: { part: THREE.Mesh<THREE.BufferGeometry, THREE.Material>; solid: THREE.Material; mist?: THREE.Material }[] = [];
  root.traverse(part => {
    if (part instanceof THREE.Mesh && part.visible && !Array.isArray(part.material)) {
      surfaces.push({ part, solid: part.material });
    }
  });
  const mistMaterials = new Map<THREE.Material, THREE.Material>();
  let previousVisibility = 1;
  function setMistVisibility(visibility: number) {
    if (visibility === previousVisibility) return;
    for (const surface of surfaces) {
      if (visibility >= 1) {
        surface.part.material = surface.solid;
      } else {
        if (!surface.mist) {
          let mist = mistMaterials.get(surface.solid);
          if (!mist) {
            mist = surface.solid.clone();
            mist.alphaHash = true;
            mistMaterials.set(surface.solid, mist);
          }
          surface.mist = mist;
        }
        surface.mist.opacity = visibility;
        surface.part.material = surface.mist;
      }
    }
    previousVisibility = visibility;
  }

  return { root, pelvis, chest, head, jaw, ears, eyes, lips, poseMouthFolds, poseBreath, tail, arms, legs, animation, setMistVisibility, hitboxes: [torsoHit, headHit] };
}

export type WolfMotion = 'stalk' | 'creep' | 'rush' | 'climb' | 'peek' | 'lunge' | 'strike';
export const strikeMoment = 0.42;

type Wolf = ReturnType<typeof createWolf>;
const target = new THREE.Vector3();
const pole = new THREE.Vector3();
const handhold = new THREE.Vector3();
const { smoothstep, lerp } = THREE.MathUtils;

export function resetWolfAnimation(wolf: Wolf) {
  wolf.animation.motion = undefined;
  wolf.animation.falling = false;
  wolf.animation.speed = 0;
  wolf.animation.supportDrop = 0;
}

export function animateWolf(
  wolf: Wolf, time: number, motion: WolfMotion, delta: number,
  groundHeight: (x: number, z: number) => number, climb?: ClimbPose,
) {
  const { root, pelvis, chest, head, jaw, ears, eyes, lips, tail, arms, legs, animation } = wolf;
  const previousMotion = animation.motion;
  const changed = previousMotion !== motion;
  const climbing = motion === 'climb';
  const running = motion === 'rush';
  const creeping = motion === 'creep';
  const peeking = motion === 'peek';
  const lunging = motion === 'lunge';
  const striking = motion === 'strike';
  const stalking = motion === 'stalk';
  const gait = running || creeping;
  const grounded = gait || stalking;
  const planted = grounded || striking;
  const wasGrounded = previousMotion === 'rush' || previousMotion === 'creep' || previousMotion === 'stalk';
  const dx = root.position.x - animation.previous.x;
  const dz = root.position.z - animation.previous.z;
  const travel = previousMotion ? Math.hypot(dx, dz) : 0;
  const speed = gait ? travel / Math.max(delta, 0.0001) : 0;
  animation.speed = THREE.MathUtils.damp(animation.speed, speed, 13, delta);
  const pace = gait ? smoothstep(animation.speed, 1.95, 4.15) : 0;
  const exertion = smoothstep(animation.speed, 0.10, 1.3);
  const stride = lerp(1.12, 2.12, pace);
  const duty = lerp(0.68, 0.44, pace);

  if (changed) {
    animation.blend = previousMotion ? 0 : 1;
    animation.motion = motion;
    if (climbing || (gait && previousMotion !== 'creep' && previousMotion !== 'rush')) {
      animation.phase = gait ? 0.075 : 0;
    }
    animation.settling = stalking && wasGrounded ? 0 : 1;
    if (animation.settling === 0) {
      const [left, right] = animation.paws;
      animation.settleFirst = left.swinging || (!right.swinging
        && left.pad.distanceToSquared(root.position) > right.pad.distanceToSquared(root.position)) ? 0 : 1;
    }
    animation.chestFrom.copy(chest.position);
    animation.pelvisFrom.copy(pelvis.position);
    animation.joints.forEach((part, index) => animation.from[index].copy(part.quaternion));
    if (planted && !wasGrounded && previousMotion !== 'strike') {
      animation.paws.forEach((paw, index) => initializePaw(paw, root, groundHeight, index === 0 ? -1 : 1));
    }
  }

  if (gait) animation.phase = (animation.phase + Math.min(0.24, travel / stride)) % 1;

  animation.previous.copy(root.position);

  const cycle = animation.phase * Math.PI * 2;
  const onRock = climb && (climbing || peeking);
  const rockCycle = climb ? climb.progress * climb.holds.cycles * Math.PI * 2 : 0;
  const atLip = peeking ? 1 : climb && climbing ? smoothstep(climb.progress, 0.905, 1) : 0;
  const sway = climbing ? Math.sin(rockCycle) * (1 - atLip) : 0;
  const fromLip = lunging ? 1 - smoothstep(time, 0, 0.31) : atLip;
  const lowPeek = peeking && climb ? 1 - climb.reveal : 0;
  const step = (animation.phase * 2) % 1;
  const load = smoothstep(step, 0, 0.23) * (1 - smoothstep(step, 0.26, 0.77));
  const spring = smoothstep(step, 0.51, 0.88) * (1 - smoothstep(step, 0.90, 1));
  const transfer = -Math.cos(cycle - 0.99) * exertion;
  const hipShift = transfer * lerp(0.089, 0.046, pace);
  const bounce = (-load * lerp(0.054, 0.112, pace) + spring * lerp(0.023, 0.069, pace)) * exertion;
  const hipHeight = grounded ? 1.045 - pace * 0.07 + bounce : 1.106;
  pelvis.position.set(grounded ? hipShift : 0, hipHeight, 0.419 - pace * 0.068);
  pelvis.rotation.set(grounded ? -pace * 0.12 + bounce * 0.54 : 0,
    grounded ? Math.sin(cycle - 0.30) * exertion * lerp(0.10, 0.14, pace) : 0,
    grounded ? -transfer * lerp(0.092, 0.045, pace) : 0);

  const reveal = peeking ? (climb?.reveal ?? smoothstep(time, 0.4, 1.6)) : 0;
  const inhale = smoothstep(reveal, 0.09, 0.38) * (1 - smoothstep(reveal, 0.43, 0.72));
  const stare = smoothstep(reveal, 0.16, 0.84);
  const breath = Math.sin(time * (peeking ? 2.85 : 2.1)) * (peeking ? 0.008 : 0.015);
  const leap = lunging ? smoothstep(time, 0.09, 0.49) * (1 - smoothstep(time, 0.72, 1)) : 0;
  const snarl = Math.max(stare * 0.69 + inhale * 0.13, leap);
  const landing = lunging ? smoothstep(time, 0.70, 1) : 0;
  const windup = striking ? smoothstep(time, 0.06, strikeMoment - 0.04) : 0;
  const swing = striking ? smoothstep(time, strikeMoment - 0.08, strikeMoment + 0.07) : 0;
  const recovery = striking ? smoothstep(time, strikeMoment + 0.08, 0.90) : 0;
  const reachAmount = windup * (1 - recovery);
  const impact = reachAmount * swing;
  const sniff = stalking ? Math.sin(time * 0.63) + 0.21 * Math.sin(time * 2.23) : 0;

  chest.position.set(
    sway * 0.063 + (grounded ? hipShift * 0.77 : 0) + sniff * 0.027 - impact * 0.076,
    1.13 + breath + inhale * 0.020 - lowPeek * 0.26 + (grounded ? hipHeight - 1.106 - bounce * 0.32 : 0) - landing * 0.17 - impact * 0.12,
    0.232 - pace * 0.12 - leap * 0.21 - impact * 0.23 - fromLip * 0.12,
  );
  chest.rotation.set(
    (onRock ? lerp(0.38, 0.18, atLip) : lerp(0.024, 0.18, fromLip)) - exertion * 0.045 - pace * 0.22 + bounce * 0.66 - leap * 0.29 - impact * 0.24,
    sway * 0.15 - pelvis.rotation.y * 0.55 + reachAmount * (0.33 - 0.59 * swing),
    sway * -0.11 + pelvis.rotation.z * 0.48 + reachAmount * (0.10 - 0.28 * swing) + leap * 0.052,
  );
  head.position.y = 0.575 + lowPeek * 0.25 - (grounded ? bounce * 0.48 : 0) + inhale * 0.012;
  head.position.z = -0.844 - leap * 0.051 - stare * 0.019;
  head.rotation.set(
    peeking ? 0.08 + breath + inhale * 0.034 - stare * 0.030 : climbing ? 0.13 - atLip * 0.03 : -0.018 + pace * 0.17 - bounce * 0.59 + leap * 0.29 + impact * 0.16 + landing * 0.21,
    sniff * 0.23 - chest.rotation.y * 0.67 + inhale * 0.045 - leap * 0.059,
    -chest.rotation.z * 0.64 + sniff * 0.046 - stare * 0.027,
  );
  const bite = lunging ? smoothstep(time, 0.13, 0.42) * (1 - smoothstep(time, 0.64, 0.90)) : 0;
  jaw.rotation.x = -(0.014 + Math.max(0, breath) * 1.6 + stare * 0.115 + inhale * 0.022 + pace * 0.11
    + bite * 0.52 + landing * 0.09 + reachAmount * 0.31);
  const blinkPhase = time % 4.91;
  const blink = (1 - stare) * smoothstep(blinkPhase, 2.4, 2.46) * (1 - smoothstep(blinkPhase, 2.46, 2.55));
  eyes.forEach(eye => { eye.scale.y = Math.max(0.08, 1 - blink - snarl * 0.21); });
  lips.forEach((lip, index) => {
    lip.rotation.x = snarl * (index === 0 ? 0.29 : 0.21);
    lip.rotation.z = (index === 0 ? -1 : 1) * snarl * 0.08;
    lip.position.y = -0.079 + snarl * 0.008;
  });
  tail.rotation.set(0.03 - pace * 0.20 - bounce * 0.80 + leap * 0.32,
    Math.sin(cycle - 1.02) * exertion * lerp(0.13, 0.16, pace) + Math.sin(time * 1.26) * 0.036,
    -transfer * 0.05);
  ears.forEach((ear, index) => {
    const side = index === 0 ? -1 : 1;
    const twitch = Math.max(0, Math.sin(time * 1.92 + index * 2.6)) ** 8;
    ear.rotation.set(-0.05 - pace * 0.26 - snarl * 0.36 - impact * 0.28 - twitch * 0.13,
      side * (0.065 + twitch * 0.19 + stare * 0.07), side * (-0.037 - snarl * 0.21));
  });

  arms.forEach((limb, index) => {
    const side = index === 0 ? -1 : 1;
    if (onRock) return;
    if (lunging) {
      const release = smoothstep(time, index ? 0.09 : 0.03, index ? 0.32 : 0.25);
      target.set(
        side * (0.32 + leap * (index ? 0.14 : 0.03) - landing * 0.13),
        -0.69 + leap * (index ? 0.42 : 0.61) - landing * 0.17,
        -0.56 - leap * (index ? 0.32 : 0.45) + landing * (index ? 0.15 : -0.20),
      );
      if (climb) target.lerp(limb.frame.worldToLocal(handhold.copy(climb.holds.lip[index])), 1 - release);
      reach(limb, target, pole.set(side * 0.68, -0.55, 0.33));
      limb.end.rotateX(lerp(1.05, leap * 0.85 + landing * 0.36, release));
      return;
    }
    if (striking) {
      const strength = index ? 0.53 : 1;
      reach(limb, target.set(
        side * (0.32 + reachAmount * strength * (0.62 - 0.88 * swing)),
        -0.91 + reachAmount * strength * (1.19 - 0.60 * swing),
        -0.35 + reachAmount * strength * (0.25 - 0.96 * swing),
      ), pole.set(side * 0.81, -0.48, 0.36));
      limb.end.rotateX(reachAmount * strength * (0.82 - swing * 1.05));
      return;
    }
    // The forelimbs trail under the shoulders and respond to each weight shift.
    const follow = Math.sin(cycle + index * Math.PI - 0.72) * exertion;
    reach(limb, target.set(
      side * (0.17 + pace * 0.07 + follow * 0.023),
      -0.98 + pace * 0.23 + follow * 0.046,
      -0.08 + pace * 0.29 + follow * lerp(0.11, 0.15, pace),
    ), pole.set(side * 0.49, 0.06, 1));
    limb.end.rotateX(0.15 + pace * 0.23 - follow * 0.085);
    limb.end.rotateY(side * 0.26);
  });

  legs.forEach((limb, index) => {
    const side = index === 0 ? -1 : 1;
    if (planted || onRock) return;
    limb.toes.rotation.x = -leap * 0.30;
    reach(limb, target.set(side * 0.04, -0.79 + leap * (index ? 0.28 : 0.39) - landing * 0.035,
      0.14 + fromLip * 0.18 + leap * (index ? 0.19 : -0.23) - landing * (index ? 0.12 : 0.27)),
      pole.set(side * 0.24, 0.04, -1));
    limb.end.rotateX(lerp(0.66, 0.09, landing) + leap * 0.11);
  });

  if (animation.blend < 1) {
    animation.blend = Math.min(1, animation.blend + delta / (lunging ? 0.09 : peeking ? 0.17 : 0.16));
    const amount = smoothstep(animation.blend, 0, 1);
    chest.position.lerpVectors(animation.chestFrom, chest.position, amount);
    pelvis.position.lerpVectors(animation.pelvisFrom, pelvis.position, amount);
    const joints = planted ? animation.bodyJoints : animation.joints;
    joints.forEach((part, index) => part.quaternion.slerpQuaternions(animation.from[index], part.quaternion, amount));
  }

  if (onRock) {
    arms.forEach((limb, index) => braceOnRock(limb, climb, index, true, peeking));
    legs.forEach((limb, index) => {
      limb.toes.rotation.x = -0.16;
      braceOnRock(limb, climb, index, false, peeking);
    });
  }

  if (planted) {
    const previousSettle = animation.settling;
    animation.settling = Math.min(1, previousSettle + delta / 0.47);
    let lower = 0;
    legs.forEach((limb, index) => {
      const side = index === 0 ? -1 : 1;
      const paw = animation.paws[index];
      if (gait) {
        stepPaw(paw, root, groundHeight, (animation.phase + index * 0.5) % 1, stride, duty, pace, side);
      } else {
        const start = index === animation.settleFirst ? 0 : 0.50;
        const progress = THREE.MathUtils.clamp((animation.settling - start) * 2, 0, 1);
        settlePaw(paw, root, groundHeight, side, progress, previousSettle <= start && progress > 0);
      }
      prepareHindLeg(limb, paw, groundHeight);
      lower = Math.max(lower, supportHeight(limb, paw));
    });
    animation.supportDrop = Math.max(lower, THREE.MathUtils.damp(animation.supportDrop, lower, 19, delta));
    pelvis.position.y -= animation.supportDrop;
    chest.position.y -= animation.supportDrop * 0.78;
    legs.forEach((limb, index) => poseHindLeg(limb, animation.paws[index], index === 0 ? -1 : 1));
  }
  wolf.poseMouthFolds();
  wolf.poseBreath(time, stare, bite);
  arms.forEach(roundLimbJoints);
  legs.forEach(roundLimbJoints);
}

export function animateWolfFall(wolf: Wolf, time: number) {
  const { animation, root, chest, head, jaw, eyes, lips, arms, legs, tail } = wolf;
  if (!animation.falling) {
    animation.falling = true;
    animation.previous.copy(root.position);
    animation.chestFrom.copy(chest.position);
    animation.joints.forEach((part, index) => animation.from[index].copy(part.quaternion));
  }

  const buckle = smoothstep(time, 0, 0.62);
  const drop = smoothstep(time, 0.16, 1);
  root.position.copy(animation.previous);
  const onCliff = animation.motion === 'climb' || animation.motion === 'peek';
  root.position.y -= onCliff ? time * time * 1.28 : buckle * (1 - drop) * 0.18;
  if (onCliff) root.position.z -= time * 0.37;
  root.rotation.z = -drop * (onCliff ? 0.42 : 1.50);
  chest.position.copy(animation.chestFrom);
  chest.position.y -= buckle * 0.20;
  chest.rotation.set(-0.26, -0.18, 0.03);
  head.rotation.set(-0.40, 0.21, 0.23);
  jaw.rotation.x = -0.18;
  eyes.forEach(eye => { eye.scale.y = 1 - buckle * 0.76; });
  lips.forEach(lip => {
    lip.rotation.x *= 1 - buckle;
    lip.rotation.z *= 1 - buckle;
  });
  tail.rotation.set(0.11, 0.23, -0.18);
  arms.forEach((limb, index) => {
    limb.first.rotation.set(index ? 0.40 : -0.28, 0.05, index ? 0.45 : -0.36);
    limb.middle.rotation.set(0.38, 0, 0);
    limb.end.rotation.set(-0.27, 0, 0.11);
  });
  legs.forEach((limb, index) => {
    limb.first.rotation.set(index ? 0.12 : -0.35, 0, index ? 0.19 : -0.12);
    limb.middle.rotation.set(index ? -0.28 : 0.41, 0, 0);
    limb.end.rotation.set(0.32, 0, 0);
  });
  animation.joints.forEach((part, index) => part.quaternion.slerpQuaternions(animation.from[index], part.quaternion, buckle));
  wolf.poseMouthFolds();
  wolf.poseBreath(0, 0, 0);
  arms.forEach(roundLimbJoints);
  legs.forEach(roundLimbJoints);
}
