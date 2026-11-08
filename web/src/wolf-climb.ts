import * as THREE from 'three';
import { reach, type WolfLimb } from './wolf-rig';

const { clamp, lerp, smoothstep } = THREE.MathUtils;
const stepSize = 1.58;
const wallRay = new THREE.Raycaster();
const out = new THREE.Vector3(0, 0, 1);
const down = new THREE.Vector3(0, -1, 0);

export function planClimb(route: THREE.CatmullRomCurve3, cliff: THREE.Object3D[], sill: THREE.Object3D[]) {
  const end = route.getPointAt(1);
  const lip = [0.43, -0.43].map(offset => {
    const point = new THREE.Vector3(end.x + offset, end.y + 1.5, -0.27);
    wallRay.set(new THREE.Vector3(point.x, end.y + 3, point.z), down);
    wallRay.near = 0;
    wallRay.far = 3;
    const surface = wallRay.intersectObjects(sill, false)[0];
    if (surface) point.y = surface.point.y;
    point.y += 0.10;
    return point;
  });

  const outerLip = lip.map(point => {
    const lower = point.clone();
    lower.y -= 0.37;
    wallRay.set(new THREE.Vector3(lower.x, lower.y, -1.23), out);
    wallRay.near = 0;
    wallRay.far = 1.06;
    const face = wallRay.intersectObjects(sill, false)[0];
    lower.z = face ? face.point.z - 0.10 : point.z - 0.41;
    return lower;
  });
  const cycles = route.getLength() / stepSize;
  const sections = Math.ceil(cycles * 5);
  const path = new THREE.CatmullRomCurve3(Array.from({ length: sections + 1 }, (_, index) => {
    const progress = index / sections;
    const point = route.getPointAt(progress);
    let clearance = point.z;
    for (const height of [0.42, 0.98, 1.53]) {
      wallRay.set(new THREE.Vector3(point.x, point.y + height, point.z - 1.32), out);
      wallRay.near = 0;
      wallRay.far = 1.74;
      const face = wallRay.intersectObjects(cliff, false)[0];
      if (face) clearance = Math.min(clearance, face.point.z - 0.36);
    }
    const ease = smoothstep(progress, 0, 0.09) * (1 - smoothstep(progress, 0.90, 1));
    point.z = lerp(point.z, Math.max(point.z - 0.91, clearance), ease);
    return point;
  }));
  const contacts = (hand: boolean) => [0, 1].map(index => {
    const offset = index * 0.5 + (hand ? 0 : 0.42);
    return Array.from({ length: Math.ceil(cycles) + 3 }, (_, step) => {
      const root = path.getPoint(clamp((step - offset + 0.29) / cycles, 0, 1));
      const x = root.x + (index === 0 ? 1 : -1) * (hand ? 0.48 : 0.31);
      const y = root.y + (hand ? 1.72 : 0.28);
      wallRay.set(new THREE.Vector3(x, y, root.z - 0.65), out);
      wallRay.near = 0;
      wallRay.far = 2.19;
      const hit = wallRay.intersectObjects(cliff, false)[0];
      const z = hit ? hit.point.z - (hand ? 0.13 : 0.22) : root.z + (hand ? 0.71 : 0.37);
      return new THREE.Vector3(x, y, z);
    });
  });

  return { path, cycles, lip, outerLip, hands: contacts(true), feet: contacts(false) };
}

export type ClimbPose = {
  holds: ReturnType<typeof planClimb>;
  progress: number;
  reveal: number;
};

const target = new THREE.Vector3();
const pole = new THREE.Vector3();

export function braceOnRock(limb: WolfLimb, pose: ClimbPose, index: number, hand: boolean, atLip: boolean) {
  const side = index === 0 ? -1 : 1;
  const { holds, progress } = pose;
  const steps = progress * holds.cycles + index * 0.5 + (hand ? 0 : 0.42);
  const i = Math.floor(steps);
  const move = smoothstep(steps - i, hand ? 0.61 : 0.65, 1);
  const clear = Math.sin(move * Math.PI);
  const contacts = (hand ? holds.hands : holds.feet)[index];
  target.lerpVectors(contacts[i], contacts[i + 1], move);
  target.y += clear * (hand ? 0.17 : 0.13);
  target.z -= clear * (hand ? 0.28 : 0.22);

  const grab = atLip ? 1 : smoothstep(progress, 0.89 + index * 0.015, 0.991);
  const press = atLip ? smoothstep(pose.reveal, 0.46 + index * 0.12, 1) : 0;
  if (hand) {
    target.lerp(holds.outerLip[index], grab).lerp(holds.lip[index], press);
  } else {
    target.y += grab * (0.23 + pose.reveal * 0.33);
    target.z += grab * 0.33;
  }
  limb.frame.worldToLocal(target);
  pole.set(side * (hand ? 0.46 : 0.29), hand ? -0.46 : 0.26, hand ? 0.37 : -0.91);
  reach(limb, target, pole);
  limb.end.rotateX(hand ? lerp(0.40 + clear * 0.19, lerp(0.58, 1.05, press), grab) : 0.81 - clear * 0.22);
  limb.end.rotateY(side * (hand ? -0.14 : 0.08));
}
