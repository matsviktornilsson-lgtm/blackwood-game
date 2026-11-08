const duration = 36;
const sampleRate = 24000;
const musicLevel = 0.28;

function frequency(note: number) {
  return 440 * 2 ** ((note - 69) / 12);
}

async function renderNightMusic() {
  const score = new OfflineAudioContext(2, duration * sampleRate, sampleRate);
  const master = score.createGain();
  master.gain.setValueAtTime(0, 0);
  master.gain.linearRampToValueAtTime(1, 0.65);
  master.gain.setValueAtTime(1, duration - 0.45);
  master.gain.linearRampToValueAtTime(0, duration);
  master.connect(score.destination);

  const bowed = score.createPeriodicWave(
    [0, 0, 0, 0, 0, 0, 0],
    [0, 1, 0.41, 0.24, 0.11, 0.065, 0.03],
  );
  const chime = score.createPeriodicWave([0, 0, 0, 0, 0, 0], [0, 1, 0.25, 0.16, 0.04, 0.12]);

  const echo = score.createDelay();
  const feedback = score.createGain();
  echo.delayTime.value = 0.39;
  feedback.gain.value = 0.25;
  echo.connect(feedback).connect(echo);
  echo.connect(master);

  // The D pedal holds under the shifting fifths and semitone tension.
  const drones = [
    [0, 36, 38, 0.105, 0],
    [0, 11, 45, 0.044, -0.52],
    [5.2, 12.4, 53, 0.035, 0.41],
    [10.4, 12, 51, 0.052, -0.34],
    [17, 11.8, 46, 0.048, 0.49],
    [21, 9.7, 57, 0.027, -0.43],
    [26, 10, 45, 0.046, -0.25],
    [29, 7, 50, 0.037, 0.36],
  ];

  for (const [start, length, note, level, pan] of drones) {
    const gain = score.createGain();
    const filter = score.createBiquadFilter();
    const stereo = score.createStereoPanner();
    const end = start + length;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(level * 0.73, start + length * 0.24);
    gain.gain.linearRampToValueAtTime(level, start + length * 0.58);
    gain.gain.linearRampToValueAtTime(0, end);
    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(360, start);
    filter.frequency.linearRampToValueAtTime(630, start + length * 0.58);
    filter.frequency.linearRampToValueAtTime(315, end);
    stereo.pan.value = pan;
    filter.connect(gain).connect(stereo).connect(master);

    for (const cents of [-4.5, 4.5]) {
      const voice = score.createOscillator();
      voice.setPeriodicWave(bowed);
      voice.frequency.value = frequency(note);
      voice.detune.value = cents;
      voice.connect(filter);
      voice.start(start);
      voice.stop(end);
    }
  }

  const accents = [
    [2.5, 62, 0.051, -0.29],
    [6.7, 57, 0.036, 0.21],
    [12.9, 63, 0.046, 0.43],
    [16.6, 62, 0.039, 0.12],
    [23.7, 53, 0.051, -0.38],
    [28.3, 65, 0.029, 0.34],
    [31.2, 62, 0.041, -0.18],
  ];
  for (const [start, note, level, pan] of accents) {
    const voice = score.createOscillator();
    const gain = score.createGain();
    const stereo = score.createStereoPanner();
    const end = start + 2.8;
    voice.setPeriodicWave(chime);
    voice.frequency.value = frequency(note);
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(level, start + 0.085);
    gain.gain.exponentialRampToValueAtTime(0.001, end);
    stereo.pan.value = pan;
    voice.connect(gain).connect(stereo).connect(master);
    stereo.connect(echo);
    voice.start(start);
    voice.stop(end);
  }

  return score.startRendering();
}

export function createNightMusic(context: AudioContext) {
  const channel = context.createGain();
  channel.gain.value = 0;
  channel.connect(context.destination);
  let playback: Promise<void> | undefined;

  return (playing: boolean) => {
    if (playing && !playback) {
      playback = renderNightMusic().then(buffer => {
        const track = context.createBufferSource();
        track.buffer = buffer;
        track.loop = true;
        track.connect(channel);
        track.start();
      }).catch(() => { playback = undefined; });
    }
    const now = context.currentTime;
    channel.gain.cancelScheduledValues(now);
    channel.gain.setTargetAtTime(playing ? musicLevel : 0, now, playing ? 0.42 : 0.15);
  };
}
