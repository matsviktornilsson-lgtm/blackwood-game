import { createNightMusic } from './music';
import { reloadCues } from './rifle-reload';
import rifleUrl from './assets/audio/rifle-shot.wav';
import boltUrl from './assets/audio/rifle-bolt.wav';
import unlockUrl from './assets/audio/rifle-unlock.wav';
import cartridgeUrl from './assets/audio/rifle-cartridge.wav';
import chamberUrl from './assets/audio/rifle-chamber.wav';
import lockUrl from './assets/audio/rifle-lock.wav';
import wolfUrl from './assets/audio/wolf-howl.wav';
import scrapeUrl from './assets/audio/claws-on-stone.wav';
import growlUrl from './assets/audio/ledge-growl.wav';
import roarUrl from './assets/audio/lunge-roar.wav';

let context: AudioContext | undefined;
let music: ReturnType<typeof createNightMusic> | undefined;

function preload(url: string) {
  return fetch(url).then(response => response.ok ? response.arrayBuffer() : undefined).catch(() => undefined);
}

const recordings = {
  shot: { bytes: preload(rifleUrl), ready: undefined as Promise<AudioBuffer | undefined> | undefined },
  bolt: { bytes: preload(boltUrl), ready: undefined as Promise<AudioBuffer | undefined> | undefined },
  unlock: { bytes: preload(unlockUrl), ready: undefined as Promise<AudioBuffer | undefined> | undefined },
  cartridge: { bytes: preload(cartridgeUrl), ready: undefined as Promise<AudioBuffer | undefined> | undefined },
  chamber: { bytes: preload(chamberUrl), ready: undefined as Promise<AudioBuffer | undefined> | undefined },
  lock: { bytes: preload(lockUrl), ready: undefined as Promise<AudioBuffer | undefined> | undefined },
  howl: { bytes: preload(wolfUrl), ready: undefined as Promise<AudioBuffer | undefined> | undefined },
  scrape: { bytes: preload(scrapeUrl), ready: undefined as Promise<AudioBuffer | undefined> | undefined },
  growl: { bytes: preload(growlUrl), ready: undefined as Promise<AudioBuffer | undefined> | undefined },
  roar: { bytes: preload(roarUrl), ready: undefined as Promise<AudioBuffer | undefined> | undefined },
};

export function enableAudio() {
  try {
    context ??= new AudioContext();
    const audio = context;
    if (audio.state === 'suspended') void audio.resume().catch(() => {});
    for (const recording of Object.values(recordings)) {
      recording.ready ??= recording.bytes
        .then(bytes => bytes ? audio.decodeAudioData(bytes) : undefined)
        .catch(() => undefined);
    }
  } catch {
    // The playtest can also be played with the visual cues alone.
  }
}

export function setMusicPlaying(playing: boolean) {
  if (playing && context) music ??= createNightMusic(context);
  music?.(playing);
}

type Playback = {
  level: number;
  pan?: number;
  lowPass?: number;
  delay?: number;
  reflection?: boolean;
  latency?: number;
  rate?: number;
};

function playRecording(recording: keyof typeof recordings, options: Playback) {
  const audio = context;
  if (!audio) return;
  const requested = audio.currentTime;
  void recordings[recording].ready?.then(buffer => {
    if (!buffer || audio.state !== 'running' || audio.currentTime - requested > (options.latency ?? 0.18)) return;
    const sample = audio.createBufferSource();
    sample.buffer = buffer;
    sample.playbackRate.value = options.rate ?? 1;
    const volume = audio.createGain();
    volume.gain.value = options.level;
    const stereo = audio.createStereoPanner();
    stereo.pan.value = options.pan ?? 0;
    volume.connect(stereo).connect(audio.destination);

    if (options.lowPass) {
      const air = audio.createBiquadFilter();
      air.type = 'lowpass';
      air.frequency.value = options.lowPass;
      sample.connect(air).connect(volume);
    } else {
      sample.connect(volume);
    }

    if (options.reflection) {
      const delay = audio.createDelay();
      delay.delayTime.value = 0.078;
      const stone = audio.createBiquadFilter();
      stone.type = 'lowpass';
      stone.frequency.value = 2300;
      const reflection = audio.createGain();
      reflection.gain.value = 0.19;
      volume.connect(delay).connect(stone).connect(reflection).connect(audio.destination);
    }

    sample.start(Math.max(audio.currentTime, requested + (options.delay ?? 0)));
  });
}

export function howl(pan: number) {
  playRecording('howl', { pan, level: 0.13, lowPass: 1850, latency: 0.9 });
}

export function clawScrape(pan: number, progress: number) {
  playRecording('scrape', {
    pan,
    level: 0.064 + progress * 0.16,
    lowPass: 1700 + progress * 3900,
    rate: 0.9 + Math.random() * 0.22,
  });
}

export function tripwireBellSound(pan: number) {
  const audio = context;
  if (!audio || audio.state !== 'running') return;
  const stereo = audio.createStereoPanner();
  stereo.pan.value = pan;
  stereo.connect(audio.destination);
  const pitch = 980 + 225 * pan;
  const start = audio.currentTime + 0.008;

  for (const [delay, strength] of [[0, 1], [0.15, 0.64]]) {
    const strike = start + delay;
    for (const [partial, level, decay] of [[1, 0.15, 0.57], [2.37, 0.072, 0.32], [3.81, 0.028, 0.15]]) {
      const tone = audio.createOscillator();
      const envelope = audio.createGain();
      tone.frequency.value = pitch * partial;
      envelope.gain.setValueAtTime(0.001, strike);
      envelope.gain.linearRampToValueAtTime(level * strength, strike + 0.003);
      envelope.gain.exponentialRampToValueAtTime(0.001, strike + decay);
      tone.connect(envelope).connect(stereo);
      tone.start(strike);
      tone.stop(strike + decay);
      if (delay > 0 && partial === 1) tone.onended = () => stereo.disconnect();
    }
  }
}

export function wolfGrowl(pan: number) {
  playRecording('growl', { pan, level: 0.34, lowPass: 4200 });
}

export function wolfRoar(pan: number) {
  playRecording('roar', { pan, level: 0.52, reflection: true });
}

export function shotSound() {
  playRecording('shot', { level: 0.59, pan: 0.10, reflection: true });
}

export function dryFireSound() {
  playRecording('lock', { level: 0.16, pan: 0.10, rate: 1.55 });
}

const reloadSounds = [
  { at: reloadCues.lift, recording: 'unlock', level: 0.23 },
  { at: reloadCues.draw, recording: 'bolt', level: 0.30 },
  { at: reloadCues.feed, recording: 'cartridge', level: 0.27 },
  { at: reloadCues.close, recording: 'chamber', level: 0.31 },
  { at: reloadCues.lock, recording: 'lock', level: 0.23 },
] as const;

export function playReloadSounds(previous: number, progress: number, rate: number) {
  for (const { at, recording, level } of reloadSounds) {
    if (previous < at && progress >= at) playRecording(recording, { level, pan: 0.15, rate });
  }
}

export function hitSound() {
  if (!context || context.state !== 'running') return;
  const start = context.currentTime + 0.085;
  const impact = context.createOscillator();
  const envelope = context.createGain();

  impact.type = 'sine';
  impact.frequency.setValueAtTime(270, start);
  impact.frequency.exponentialRampToValueAtTime(95, start + 0.12);
  envelope.gain.setValueAtTime(0.16, start);
  envelope.gain.exponentialRampToValueAtTime(0.001, start + 0.16);
  impact.connect(envelope).connect(context.destination);
  impact.start(start);
  impact.stop(start + 0.16);
}

export function playerHitSound() {
  if (!context || context.state !== 'running') return;
  const start = context.currentTime;
  const impact = context.createOscillator();
  const filter = context.createBiquadFilter();
  const envelope = context.createGain();

  impact.type = 'sawtooth';
  impact.frequency.setValueAtTime(106, start);
  impact.frequency.exponentialRampToValueAtTime(41, start + 0.22);
  filter.type = 'lowpass';
  filter.frequency.setValueAtTime(800, start);
  filter.frequency.exponentialRampToValueAtTime(130, start + 0.21);
  envelope.gain.setValueAtTime(0.16, start);
  envelope.gain.exponentialRampToValueAtTime(0.001, start + 0.26);
  impact.connect(filter).connect(envelope).connect(context.destination);
  impact.start(start);
  impact.stop(start + 0.26);
}
