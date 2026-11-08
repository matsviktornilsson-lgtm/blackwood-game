import * as THREE from 'three';

const cube = new THREE.BoxGeometry(1, 1, 1);

export function box(parent: THREE.Object3D, w: number, h: number, d: number, x: number, y: number, z: number, material: THREE.Material) {
  const mesh = new THREE.Mesh(cube, material);
  mesh.scale.set(w, h, d);
  mesh.position.set(x, y, z);
  parent.add(mesh);
  return mesh;
}

export function scatter(seed: number) {
  const value = Math.sin(seed * 127.1) * 43758.5453;
  return value - Math.floor(value);
}
