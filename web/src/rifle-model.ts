import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { weatheredWood } from './lookout-materials';
import { createReloadProps } from './rifle-reload';

type StockSection = readonly [z: number, center: number, width: number, height: number];

function stockGeometry(sections: readonly StockSection[]) {
  const points: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];
  const sides = 24;
  sections.forEach(([z, center, width, height], ring) => {
    for (let i = 0; i <= sides; i++) {
      const angle = i / sides * Math.PI * 2;
      const x = Math.cos(angle);
      const y = Math.sin(angle);
      points.push(
        Math.sign(x) * Math.abs(x) ** 0.82 * width,
        center + Math.sign(y) * Math.abs(y) ** 0.77 * height,
        z,
      );
      uvs.push(i / sides * 0.86, 0.49 - z * 1.04);
      if (ring === 0 || i === 0) continue;
      const a = (ring - 1) * (sides + 1) + i - 1;
      const b = a + sides + 1;
      indices.push(a, b, b + 1, a, b + 1, a + 1);
    }
  });

  for (const ring of [0, sections.length - 1]) {
    const [z, center] = sections[ring];
    const cap = points.length / 3;
    const offset = ring * (sides + 1);
    points.push(0, center, z);
    uvs.push(0.45, 0.49 - z * 1.04);
    for (let i = 0; i < sides; i++) {
      if (ring === 0) indices.push(cap, offset + i, offset + i + 1);
      else indices.push(cap, offset + i + 1, offset + i);
    }
  }

  const shape = new THREE.BufferGeometry();
  shape.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
  shape.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  shape.setIndex(indices);
  shape.computeVertexNormals();
  return shape;
}

export function createRifleModel() {
  const model = new THREE.Group();
  model.name = 'Lookout bolt-action rifle';
  const walnut = weatheredWood('#d2ad85');
  walnut.roughness = 0.57;
  walnut.bumpScale = 0.0034;
  const blued = new THREE.MeshStandardMaterial({ color: '#313a41', metalness: 0.70, roughness: 0.40 });
  const machined = new THREE.MeshStandardMaterial({ color: '#646a6b', metalness: 0.62, roughness: 0.36 });
  const parkerized = new THREE.MeshStandardMaterial({ color: '#24292a', metalness: 0.52, roughness: 0.58 });
  const rubber = new THREE.MeshStandardMaterial({ color: '#20201d', roughness: 0.87 });
  const dark = new THREE.MeshStandardMaterial({ color: '#090c0e', roughness: 0.84 });
  const glass = new THREE.MeshPhysicalMaterial({
    color: '#244956', metalness: 0.48, roughness: 0.21,
    clearcoat: 0.78, clearcoatRoughness: 0.23,
  });

  function add(shape: THREE.BufferGeometry, material: THREE.Material, x: number, y: number, z: number, parent = model) {
    const mesh = new THREE.Mesh(shape, material);
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  }

  function cylinder(front: number, rear: number, length: number, y: number, z: number, material: THREE.Material, open = false) {
    const part = add(new THREE.CylinderGeometry(rear, front, length, 28, 1, open), material, 0, y, z);
    part.rotation.x = Math.PI / 2;
  }

  function housing(w: number, h: number, d: number, x: number, y: number, z: number, material: THREE.Material) {
    return add(new RoundedBoxGeometry(w, h, d, 2, Math.min(w, h, d) * 0.24), material, x, y, z);
  }

  model.add(new THREE.Mesh(stockGeometry([
    [0.365, -0.118, 0.029, 0.068],
    [0.344, -0.116, 0.033, 0.070],
    [0.290, -0.107, 0.035, 0.065],
    [0.208, -0.084, 0.033, 0.055],
    [0.144, -0.063, 0.028, 0.044],
    [0.093, -0.058, 0.032, 0.042],
    [0.037, -0.050, 0.038, 0.036],
    [-0.073, -0.034, 0.041, 0.036],
    [-0.210, -0.037, 0.039, 0.030],
    [-0.330, -0.039, 0.033, 0.026],
    [-0.450, -0.043, 0.026, 0.023],
    [-0.512, -0.043, 0.021, 0.017],
    [-0.530, -0.043, 0.014, 0.011],
  ]), walnut));
  model.add(new THREE.Mesh(stockGeometry([
    [0.391, -0.122, 0.025, 0.064],
    [0.383, -0.120, 0.029, 0.068],
    [0.363, -0.118, 0.030, 0.069],
  ]), rubber));

  cylinder(0.028, 0.028, 0.066, 0.017, -0.116, blued);
  cylinder(0.029, 0.029, 0.049, 0.017, 0.051, blued);
  const receiver = add(new THREE.CylinderGeometry(0.029, 0.028, 0.111, 32, 1, true, 3.03, 4.1),
    blued, 0, 0.017, -0.028);
  receiver.rotation.x = Math.PI / 2;
  housing(0.039, 0.010, 0.102, 0, 0.014, -0.028, dark);
  housing(0.006, 0.009, 0.102, 0.024, 0.025, -0.028, machined);
  cylinder(0.021, 0.027, 0.119, 0.017, -0.200, blued);
  cylinder(0.0118, 0.0198, 0.456, 0.017, -0.482, blued);
  cylinder(0.0114, 0.0123, 0.058, 0.017, -0.726, blued, true);
  cylinder(0.0085, 0.0087, 0.012, 0.017, -0.746, dark);
  const crown = add(new THREE.RingGeometry(0.007, 0.0115, 28), machined, 0, 0.017, -0.755);
  crown.rotation.y = Math.PI;


  const bolt = new THREE.Group();
  const boltRest = 0.077;
  bolt.position.set(0, 0.021, boltRest);
  model.add(bolt);
  const shank = add(new THREE.CylinderGeometry(0.0155, 0.016, 0.147, 24), machined, 0, 0, -0.066, bolt);
  shank.rotation.x = Math.PI / 2;
  const cap = add(new THREE.CylinderGeometry(0.0185, 0.020, 0.028, 24), blued, 0, 0, 0.011, bolt);
  cap.rotation.x = Math.PI / 2;
  const handle = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0.018, 0.002, 0),
    new THREE.Vector3(0.042, -0.002, 0.015),
    new THREE.Vector3(0.053, -0.023, 0.035),
    new THREE.Vector3(0.063, -0.043, 0.053),
  ]);
  add(new THREE.TubeGeometry(handle, 14, 0.0062, 9, false), machined, 0, 0, 0, bolt);
  const knob = add(new THREE.SphereGeometry(0.014, 14, 9), blued, 0.065, -0.045, 0.054, bolt);
  knob.scale.set(0.87, 1.05, 1.18);

  const guard = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0, -0.067, -0.071),
    new THREE.Vector3(0, -0.117, -0.057),
    new THREE.Vector3(0, -0.133, 0.004),
    new THREE.Vector3(0, -0.111, 0.067),
    new THREE.Vector3(0, -0.081, 0.080),
  ]);
  add(new THREE.TubeGeometry(guard, 22, 0.0056, 8, false), blued, 0, 0, 0);
  const trigger = add(new THREE.TorusGeometry(0.022, 0.0045, 7, 15, Math.PI * 0.71), machined, 0, -0.086, 0.022);
  trigger.rotation.y = Math.PI / 2;
  trigger.rotation.x = 0.42;

  const opticY = 0.095;
  cylinder(0.0187, 0.0187, 0.37, opticY, -0.024, parkerized);
  cylinder(0.036, 0.020, 0.088, opticY, -0.225, blued);
  cylinder(0.038, 0.036, 0.052, opticY, -0.293, blued, true);
  cylinder(0.032, 0.031, 0.007, opticY, -0.303, glass);
  cylinder(0.019, 0.0315, 0.070, opticY, 0.149, blued);
  cylinder(0.0325, 0.034, 0.046, opticY, 0.200, parkerized, true);
  cylinder(0.027, 0.028, 0.009, opticY, 0.214, glass);
  cylinder(0.0338, 0.0345, 0.012, opticY, 0.216, parkerized, true);
  for (const z of [-0.142, 0.091]) {
    housing(0.048, 0.052, 0.035, 0, 0.062, z, blued);
    cylinder(0.023, 0.023, 0.028, opticY, z, machined);
    const screw = add(new THREE.CylinderGeometry(0.006, 0.006, 0.004, 12), dark, 0.025, 0.091, z);
    screw.rotation.z = Math.PI / 2;
  }
  add(new THREE.CylinderGeometry(0.018, 0.017, 0.023, 20), parkerized, 0, 0.126, -0.013);
  const turret = add(new THREE.CylinderGeometry(0.014, 0.016, 0.013, 16), blued, 0.027, opticY, -0.013);
  turret.rotation.z = Math.PI / 2;

  const poseProps = createReloadProps(model);
  function poseReload(time: number) {
    const rise = THREE.MathUtils.smoothstep(time, 0.09, 0.20) * (1 - THREE.MathUtils.smoothstep(time, 0.82, 0.93));
    const travel = THREE.MathUtils.smoothstep(time, 0.20, 0.33) * (1 - THREE.MathUtils.smoothstep(time, 0.69, 0.83));
    bolt.rotation.z = rise * 1.06;
    bolt.position.z = boltRest + travel * 0.117;
    poseProps(time, bolt, knob);
  }

  return { model, poseReload };
}
