import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

export const reloadDuration = 1.35;
export const reloadCues = { lift: 0.11, draw: 0.23, feed: 0.58, close: 0.73, lock: 0.89 } as const;

const { lerp, smoothstep } = THREE.MathUtils;
const forward = new THREE.Vector3(0, 0, -1);
const backward = new THREE.Vector3(0, 0, 1);
const wristOffset = new THREE.Vector3(0, 0.002, 0.058);
const forearmDirection = new THREE.Vector3(0.48, -0.55, 0.67).normalize();
const forearmAim = new THREE.Vector3();
const caseTravel = new THREE.Vector3();
const viewRotation = new THREE.Quaternion();
const reach = new THREE.Vector3();
const work = new THREE.Vector3();
const latch = new THREE.Vector3();

export function createReloadProps(rifle: THREE.Group) {
  const leather = new THREE.MeshStandardMaterial({ color: '#40352c', roughness: 0.91 });
  const pads = new THREE.MeshStandardMaterial({ color: '#292722', roughness: 0.96 });
  const sleeve = new THREE.MeshStandardMaterial({ color: '#403f36', roughness: 1 });
  const brass = new THREE.MeshStandardMaterial({ color: '#c3a158', metalness: 0.55, roughness: 0.38 });
  const copper = new THREE.MeshStandardMaterial({ color: '#b06b49', metalness: 0.48, roughness: 0.41 });
  const primer = new THREE.MeshStandardMaterial({ color: '#7a7370', metalness: 0.61, roughness: 0.38 });

  function part(parent: THREE.Group, geometry: THREE.BufferGeometry, material: THREE.Material, x: number, y: number, z: number) {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  }

  const hand = new THREE.Group();
  hand.name = 'Reloading hand';
  rifle.add(hand);
  part(hand, new RoundedBoxGeometry(0.074, 0.036, 0.092, 3, 0.013), leather, 0, 0, 0.013);
  part(hand, new RoundedBoxGeometry(0.069, 0.021, 0.048, 2, 0.008), pads, 0, 0.013, -0.005);
  const sleeveRoot = new THREE.Group();
  sleeveRoot.name = 'Reloading forearm';
  rifle.add(sleeveRoot);
  const forearm = part(sleeveRoot, new THREE.CylinderGeometry(0.047, 0.032, 0.41, 18), sleeve, 0, 0, 0.197);
  forearm.rotation.x = Math.PI / 2;
  forearm.scale.z = 0.79;
  part(hand, new RoundedBoxGeometry(0.078, 0.052, 0.025, 2, 0.014), pads, 0, 0.002, 0.051);

  const fingers = [-0.027, -0.009, 0.009, 0.027].map((x, index) => {
    const knuckle = new THREE.Group();
    knuckle.position.set(x, -0.005, -0.025 + Math.max(0, index - 1) * 0.004);
    hand.add(knuckle);
    const length = [0.033, 0.038, 0.034, 0.027][index];
    part(knuckle, new RoundedBoxGeometry(0.017, 0.018, length, 2, 0.007), leather, 0, 0, -length * 0.37);
    const tip = new THREE.Group();
    tip.position.z = -length * 0.77;
    knuckle.add(tip);
    part(tip, new RoundedBoxGeometry(0.015, 0.016, length * 0.86, 2, 0.007), pads, 0, 0, -length * 0.33);
    return { knuckle, tip };
  });
  const thumb = new THREE.Group();
  thumb.position.set(-0.034, -0.014, 0.019);
  hand.add(thumb);
  part(thumb, new RoundedBoxGeometry(0.021, 0.021, 0.046, 2, 0.009), leather, 0, 0, -0.015);
  part(thumb, new RoundedBoxGeometry(0.018, 0.019, 0.028, 2, 0.009), pads, 0.002, -0.003, -0.040);

  function makeCartridge(live: boolean) {
    const round = new THREE.Group();
    round.name = live ? 'Fresh cartridge' : 'Spent case';
    rifle.add(round);
    function turned(front: number, rear: number, length: number, z: number, material: THREE.Material, open = false) {
      part(round, new THREE.CylinderGeometry(rear, front, length, 20, 1, open), material, 0, 0, z).rotation.x = Math.PI / 2;
    }
    turned(0.0058, 0.0066, 0.042, 0.004, brass);
    turned(0.0045, 0.0058, 0.006, -0.020, brass);
    turned(0.0044, 0.0045, 0.009, -0.027, brass, !live);
    turned(0.0068, 0.0068, 0.003, 0.025, brass);
    turned(0.0021, 0.0021, 0.001, 0.027, primer);
    if (live) {
      turned(0.0027, 0.0043, 0.012, -0.037, copper);
      turned(0.0008, 0.0027, 0.006, -0.046, copper);
    }
    return round;
  }

  const cartridge = makeCartridge(true);
  const spent = makeCartridge(false);
  const from = new THREE.Vector3(0.226, 0.058, 0.127);
  const feedStart = new THREE.Vector3(0.062, 0.061, 0.022);
  const tray = new THREE.Vector3(0.006, 0.033, -0.006);

  function pose(time: number, bolt: THREE.Group, knob: THREE.Mesh) {
    const active = time > 0 && time < 1;
    hand.visible = sleeveRoot.visible = active;
    cartridge.visible = active && time >= 0.40 && time < 0.86;
    spent.visible = active && time >= 0.28 && time < 0.55;
    if (!active) return;

    viewRotation.copy(rifle.quaternion).invert();
    const eject = (time - 0.28) / 0.27;
    if (spent.visible) {
      caseTravel.set(eject * 0.67, eject * 0.22 - eject * eject * 0.48, eject * 0.16)
        .applyQuaternion(viewRotation);
      spent.position.set(0.012, 0.041, 0.005).add(caseTravel);
      spent.rotation.set(eject * 4.1, eject * 7.8, eject * 4.6);
    }

    const reachIn = smoothstep(time, 0.40, 0.54);
    const seat = smoothstep(time, 0.53, 0.64);
    const chamber = smoothstep(time, 0.70, 0.85);
    cartridge.position.lerpVectors(from, feedStart, reachIn).lerp(tray, seat);
    cartridge.position.z -= chamber * 0.079;
    cartridge.rotation.set((1 - seat) * 0.24, (1 - seat) * -0.47, (1 - seat) * 0.36);

    const grip = smoothstep(time, 0.03, 0.12) * (1 - smoothstep(time, 0.90, 1));
    const loading = smoothstep(time, 0.32, 0.44) * (1 - smoothstep(time, 0.63, 0.72));
    latch.copy(knob.position).applyQuaternion(bolt.quaternion).add(bolt.position);
    work.copy(latch).lerp(cartridge.position, loading);
    work.y += loading * 0.004;
    hand.position.set(
      work.x + lerp(0.027, 0.036, loading) + (1 - grip) * 0.15,
      work.y + lerp(0.020, 0.023, loading) - (1 - grip) * 0.19,
      work.z + lerp(0.053, 0.061, loading) + (1 - grip) * 0.12,
    );
    reach.subVectors(work, hand.position).normalize();
    hand.quaternion.setFromUnitVectors(forward, reach);
    hand.rotateZ(lerp(-0.32, -0.83, loading));
    sleeveRoot.position.copy(wristOffset).applyQuaternion(hand.quaternion).add(hand.position);
    forearmAim.copy(forearmDirection).applyQuaternion(viewRotation);
    sleeveRoot.quaternion.setFromUnitVectors(backward, forearmAim);

    fingers.forEach(({ knuckle, tip }, index) => {
      const pinch = index === 0 ? 0.32 : 0.68 + index * 0.12;
      knuckle.rotation.x = -lerp(0.55, pinch, loading) * grip;
      tip.rotation.x = -lerp(0.72, pinch * 0.76, loading) * grip;
    });
    thumb.rotation.set(-0.39 - loading * 0.21, 0.44 - loading * 0.41, 0.22);
  }

  hand.visible = sleeveRoot.visible = cartridge.visible = spent.visible = false;
  return pose;
}
