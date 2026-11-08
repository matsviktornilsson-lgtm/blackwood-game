import * as THREE from 'three';

let cloud: THREE.CanvasTexture | undefined;

function breathTexture() {
  if (cloud) return cloud;
  const canvas = document.createElement('canvas');
  canvas.width = 96;
  canvas.height = 72;
  const paint = canvas.getContext('2d')!;
  for (const [x, y, radius, density] of [[34, 39, 25, 0.42], [52, 32, 27, 0.61], [67, 40, 17, 0.26], [44, 49, 19, 0.29]]) {
    const fog = paint.createRadialGradient(x, y, 0, x, y, radius);
    fog.addColorStop(0, `rgba(255,255,255,${density})`);
    fog.addColorStop(0.57, `rgba(255,255,255,${density * 0.48})`);
    fog.addColorStop(1, 'rgba(255,255,255,0)');
    paint.fillStyle = fog;
    paint.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  }
  cloud = new THREE.CanvasTexture(canvas);
  return cloud;
}

export function createWolfBreath(head: THREE.Group) {
  const puffs = [0, 1, 2].map(() => {
    const puff = new THREE.Sprite(new THREE.SpriteMaterial({
      map: breathTexture(), color: '#a4b6c3', depthWrite: false, transparent: true, toneMapped: false,
    }));
    puff.visible = false;
    head.add(puff);
    return puff;
  });
  const { clamp, smoothstep } = THREE.MathUtils;

  return (time: number, growl: number, bite: number) => {
    puffs.forEach((puff, i) => {
      const age = bite > 0 ? clamp((time - 0.19) * 2.1 - i * 0.12, 0, 1) : (time * 0.69 + i * 0.17) % 1;
      const taper = smoothstep(age, 0, 0.27) * (1 - smoothstep(age, 0.29, 1));
      const strength = Math.max(growl * 0.12, bite * 0.17) * taper;
      puff.visible = strength > 0.008;
      if (!puff.visible) return;
      const spread = 0.11 + age * (bite > 0 ? 0.32 : 0.28);
      puff.position.set(Math.sin(i * 2.3 + age * 2.9) * age * 0.057, -0.105 + age * 0.12,
        -0.54 - age * (bite > 0 ? 0.49 : 0.40));
      puff.scale.set(spread * 1.42, spread * 0.88, 1);
      puff.material.opacity = strength;
      puff.material.rotation = (i - 1) * 0.45 + age * 0.31;
    });
  };
}
