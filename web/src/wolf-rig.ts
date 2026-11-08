import * as THREE from 'three';

type Point = readonly [number, number, number];

export type WolfLimb = {
  frame: THREE.Group;
  first: THREE.Bone;
  middle: THREE.Bone;
  end: THREE.Bone;
  upper: THREE.Vector3;
  lower: THREE.Vector3;
  bendSkin: THREE.Bone;
  tipSkin: THREE.Bone;
};

function weighSurface(geometry: THREE.BufferGeometry, bend: number, tip: number) {
  if (geometry.hasAttribute('skinIndex')) return;
  const along = geometry.attributes.limbY;
  const weights = new Float32Array(along.count * 4);
  const joints = new Uint16Array(along.count * 4);
  const { smoothstep } = THREE.MathUtils;

  for (let i = 0; i < along.count; i++) {
    const y = -along.getX(i);
    const root = smoothstep(y, -0.14, 0.13);
    const joint = smoothstep(y, bend - 0.14, bend + 0.14);
    const distal = smoothstep(y, tip - 0.125, tip + 0.117);
    // Each rounded joint has a bone halfway between its two segment rotations.
    const mix = root < 1 ? root : distal > 0 ? distal * 2 : joint * 2;
    const start = root < 1 ? 0 : distal > 0 ? 3 : 1;
    const slot = Math.min(1, Math.floor(mix));
    const weight = mix - slot;
    const offset = i * 4;
    joints[offset] = start + slot;
    joints[offset + 1] = start + slot + 1;
    weights[offset] = 1 - weight;
    weights[offset + 1] = weight;
  }

  geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(joints, 4));
  geometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(weights, 4));
}

export function skinLimb(
  parent: THREE.Object3D, geometry: THREE.BufferGeometry, material: THREE.Material,
  origin: Point, middleOffset: Point, endOffset: Point, fur?: { geometry: THREE.BufferGeometry; material: THREE.Material },
) {
  const frame = new THREE.Group();
  frame.position.set(...origin);
  parent.add(frame);

  const anchor = new THREE.Bone();
  const first = new THREE.Bone();
  const middle = new THREE.Bone();
  const end = new THREE.Bone();
  const bendSkin = new THREE.Bone();
  const tipSkin = new THREE.Bone();
  middle.position.set(...middleOffset);
  end.position.set(...endOffset);
  bendSkin.position.copy(middle.position);
  tipSkin.position.copy(end.position);
  first.add(middle, bendSkin);
  middle.add(end, tipSkin);

  const skin = new THREE.SkinnedMesh(geometry, material);
  skin.add(anchor, first);
  frame.add(skin);
  frame.updateWorldMatrix(true, true);
  const skeleton = new THREE.Skeleton([anchor, first, bendSkin, middle, tipSkin, end]);
  const bend = -middle.position.y;
  const tip = bend - end.position.y;

  function bind(surface: THREE.SkinnedMesh) {
    weighSurface(surface.geometry, bend, tip);
    surface.bind(skeleton, frame.matrixWorld);
    if (!surface.geometry.boundingSphere) surface.geometry.computeBoundingSphere();
    surface.boundingSphere = surface.geometry.boundingSphere!.clone();
    surface.boundingSphere.radius += 0.48;
  }
  bind(skin);
  if (fur) {
    const pelt = new THREE.SkinnedMesh(fur.geometry, fur.material);
    frame.add(pelt);
    bind(pelt);
  }
  return { frame, first, middle, end, upper: middle.position.clone(), lower: end.position.clone(), bendSkin, tipSkin };
}

export function roundLimbJoints(limb: WolfLimb) {
  limb.bendSkin.quaternion.identity().slerp(limb.middle.quaternion, 0.5);
  limb.tipSkin.quaternion.identity().slerp(limb.end.quaternion, 0.5);
}

const axis = new THREE.Vector3();
const bendDirection = new THREE.Vector3();
const knee = new THREE.Vector3();
const firstDirection = new THREE.Vector3();
const restDirection = new THREE.Vector3();
const secondDirection = new THREE.Vector3();
const inverse = new THREE.Quaternion();

export function reach(limb: WolfLimb, target: THREE.Vector3, pole: THREE.Vector3) {
  const length = target.length();
  if (length < 0.00001) return;
  const upper = limb.upper.length();
  const lower = limb.lower.length();
  const distance = THREE.MathUtils.clamp(length, Math.abs(upper - lower) + 0.003, upper + lower - 0.003);
  axis.copy(target).divideScalar(length);
  bendDirection.copy(pole).addScaledVector(axis, -pole.dot(axis)).normalize();

  const along = (upper ** 2 + distance ** 2 - lower ** 2) / (2 * distance);
  const height = Math.sqrt(Math.max(0, upper ** 2 - along ** 2));
  knee.copy(axis).multiplyScalar(along).addScaledVector(bendDirection, height);
  limb.first.quaternion.setFromUnitVectors(restDirection.copy(limb.upper).normalize(), firstDirection.copy(knee).normalize());
  inverse.copy(limb.first.quaternion).invert();
  secondDirection.copy(axis).multiplyScalar(distance).sub(knee).applyQuaternion(inverse).normalize();
  limb.middle.quaternion.setFromUnitVectors(restDirection.copy(limb.lower).normalize(), secondDirection);
  limb.end.quaternion.copy(limb.first.quaternion).multiply(limb.middle.quaternion).invert();
}
