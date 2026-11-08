import * as THREE from 'three';
import { box } from './geometry';

const iron = new THREE.MeshStandardMaterial({ color: '#494238', metalness: 0.65, roughness: 0.58 });
const brass = new THREE.MeshStandardMaterial({ color: '#c79c54', metalness: 0.48, roughness: 0.39 });
const bellShape = new THREE.LatheGeometry([
  [0.032, 0.119], [0.048, 0.093], [0.056, 0.048], [0.073, 0.016],
  [0.079, 0], [0.091, 0.004], [0.084, 0.01], [0.065, 0.043],
  [0.058, 0.094], [0.049, 0.12], [0.029, 0.133],
].map(([radius, y]) => new THREE.Vector2(radius, y)), 20);
const clapperShape = new THREE.SphereGeometry(0.018, 10, 8);
const wireShape = new THREE.BufferGeometry().setFromPoints([
  new THREE.Vector3(-0.12, 0.26, 0),
  new THREE.Vector3(-0.24, 0.18, -0.13),
  new THREE.Vector3(-0.72, 0.07, -0.25),
  new THREE.Vector3(-1.14, -0.18, -0.31),
]);
const wireMaterial = new THREE.LineBasicMaterial({ color: '#958478' });

export function createTripwireBell(room: THREE.Group, x: number, lane: string) {
  const rig = new THREE.Group();
  rig.name = lane + ' tripwire bell';
  rig.position.set(x + 0.73, 0, 0.12);
  box(rig, 0.06, 0.48, 0.065, 0, 0.23, 0, iron);
  box(rig, 0.21, 0.035, 0.055, -0.074, 0.47, 0, iron);
  const bell = new THREE.Mesh(bellShape, brass);
  bell.position.set(-0.12, 0.32, 0);
  const clapper = new THREE.Mesh(clapperShape, iron);
  clapper.position.set(-0.12, 0.32, 0);
  rig.add(bell, clapper, new THREE.Line(wireShape, wireMaterial));
  rig.visible = false;
  room.add(rig);
  return rig;
}
