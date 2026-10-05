import { useCallback, useEffect, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { Image } from 'expo-image';
import { CameraView, useCameraPermissions, type CameraType } from 'expo-camera';
import { useKeepAwake } from 'expo-keep-awake';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { RosBridge, stampNow, type ConnState } from './src/rosbridge';
import { colors } from './src/theme';

const TOPIC_INPUT = '/cv/image/compressed';
const TOPIC_ANNOTATED = '/cv/annotated/compressed';
const TOPIC_STATS = '/cv/stats';
const TOPIC_CONFIG = '/cv/overlay_config';
const IMG_TYPE = 'sensor_msgs/msg/CompressedImage';
const STR_TYPE = 'std_msgs/msg/String';
const MAX_FPS = 12;
const STORE_KEY = 'vision-ros/settings';
const DEVICE_ID = `${Platform.OS}-${Math.random().toString(36).slice(2, 6)}`;

type Mode = 'stream' | 'watch';
type Overlay = { boxes: boolean; skeleton: boolean; heatmap: boolean };
type Stats = {
  fps: number;
  motion_level: number;
  motion_regions: number;
  hands: { handedness: string; gesture: string; fingers: number }[];
  source: string;
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Pick a small capture size (~640px) so frames are quick to grab and send. */
function pickPictureSize(sizes: string[]): string | undefined {
  const parsed = sizes
    .map((s) => {
      const m = /^(\d+)x(\d+)$/.exec(s);
      return m ? { s, w: +m[1], h: +m[2] } : null;
    })
    .filter((v): v is { s: string; w: number; h: number } => !!v);
  const ok = parsed.filter((p) => Math.max(p.w, p.h) >= 480).sort((a, b) => a.w * a.h - b.w * b.h);
  if (ok.length) return ok[0].s;
  if (sizes.includes('640x480')) return '640x480';
  return sizes.find((s) => /medium|low|vga/i.test(s));
}

export default function App() {
  return (
    <SafeAreaProvider>
      <Main />
    </SafeAreaProvider>
  );
}

function Main() {
  const [host, setHost] = useState(Platform.OS === 'web' ? 'localhost' : '');
  const [port, setPort] = useState('9090');
  const [conn, setConn] = useState<ConnState>('idle');
  const [connErr, setConnErr] = useState('');
  const [mode, setMode] = useState<Mode>('stream');
  const [facing, setFacing] = useState<CameraType>(Platform.OS === 'web' ? 'front' : 'back');
  const [overlay, setOverlay] = useState<Overlay>({ boxes: true, skeleton: true, heatmap: true });
  const [frame, setFrame] = useState<string | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [sentFps, setSentFps] = useState(0);
  const [camReady, setCamReady] = useState(false);
  const [pictureSize, setPictureSize] = useState<string>();
  const [permission, requestPermission] = useCameraPermissions();

  const bridge = useRef<RosBridge | null>(null);
  const camRef = useRef<CameraView>(null);
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;

  const streaming = conn === 'connected' && mode === 'stream' && camReady && !!permission?.granted;

  // Restore saved connection settings.
  useEffect(() => {
    AsyncStorage.getItem(STORE_KEY)
      .then((raw) => {
        if (!raw) return;
        const s = JSON.parse(raw);
        if (s.host) setHost(s.host);
        if (s.port) setPort(s.port);
        if (s.mode) setMode(s.mode);
        if (s.overlay) setOverlay(s.overlay);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    AsyncStorage.setItem(STORE_KEY, JSON.stringify({ host, port, mode, overlay })).catch(() => {});
  }, [host, port, mode, overlay]);

  const disconnect = useCallback(() => {
    bridge.current?.close();
    bridge.current = null;
    setFrame(null);
    setStats(null);
  }, []);

  const connect = useCallback(() => {
    disconnect();
    const h = host.trim().replace(/^wss?:\/\//, '').replace(/\/.*$/, '');
    if (!h) {
      setConn('error');
      setConnErr('Enter the IP address of the computer running ROS2');
      return;
    }
    const url = h.includes(':') ? `ws://${h}` : `ws://${h}:${port.trim() || '9090'}`;
    const b = new RosBridge(url);
    b.onState = (s, err) => {
      setConn(s);
      setConnErr(err ?? '');
      if (s === 'connected') b.publish(TOPIC_CONFIG, STR_TYPE, { data: JSON.stringify(overlayRef.current) });
    };
    b.subscribe(TOPIC_ANNOTATED, IMG_TYPE, (m) => setFrame(`data:image/jpeg;base64,${m.data}`), {
      queue_length: 1,
      throttle_rate: 33,
    });
    b.subscribe(TOPIC_STATS, STR_TYPE, (m) => {
      try {
        setStats(JSON.parse(m.data));
      } catch {}
    }, { queue_length: 1, throttle_rate: 250 });
    bridge.current = b;
    b.connect();
  }, [host, port, disconnect]);

  useEffect(() => disconnect, [disconnect]);

  // The camera view unmounts in watch mode; wait for it to report ready again before capturing.
  useEffect(() => {
    if (mode !== 'stream') setCamReady(false);
  }, [mode]);

  // Push overlay toggles to the overlay node whenever they change.
  useEffect(() => {
    bridge.current?.publish(TOPIC_CONFIG, STR_TYPE, { data: JSON.stringify(overlay) });
  }, [overlay]);

  // Capture loop: grab a frame, publish it, repeat (capped at MAX_FPS, backs off if the socket is congested).
  useEffect(() => {
    if (!streaming) {
      setSentFps(0);
      return;
    }
    let alive = true;
    const times: number[] = [];
    (async () => {
      while (alive) {
        const t0 = Date.now();
        const b = bridge.current;
        if (!b || !camRef.current) break;
        if (b.buffered > 256 * 1024) {
          await sleep(30);
          continue;
        }
        try {
          const pic = await camRef.current.takePictureAsync({
            base64: true,
            quality: 0.5,
            imageType: 'jpg',
            shutterSound: false,
          });
          const b64 = pic?.base64 ? pic.base64.slice(pic.base64.indexOf(',') + 1) : '';
          if (alive && b64) {
            b.publish(TOPIC_INPUT, IMG_TYPE, {
              header: { stamp: stampNow(), frame_id: DEVICE_ID },
              format: 'jpeg',
              data: b64,
            });
            const now = Date.now();
            times.push(now);
            while (times.length && now - times[0] > 2000) times.shift();
            setSentFps(times.length / 2);
          }
        } catch {
          await sleep(200);
        }
        await sleep(Math.max(0, 1000 / MAX_FPS - (Date.now() - t0)));
      }
    })();
    return () => {
      alive = false;
    };
  }, [streaming]);

  const onCameraReady = useCallback(async () => {
    setCamReady(true);
    if (Platform.OS === 'web') return;
    try {
      const sizes = (await camRef.current?.getAvailablePictureSizesAsync()) ?? [];
      setPictureSize(pickPictureSize(sizes));
    } catch {}
  }, []);

  const needCamera = mode === 'stream';
  const connected = conn === 'connected';

  return (
    <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
      <StatusBar style="light" />
      {streaming || connected ? <KeepAwake /> : null}
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <Text style={styles.title}>Vision ROS</Text>
            <View style={styles.statusPill}>
              <View style={[styles.dot, { backgroundColor: dotColor(conn) }]} />
              <Text style={styles.statusText}>{statusLabel(conn)}</Text>
            </View>
          </View>

          <View style={styles.card}>
            <Text style={styles.label}>ROS2 computer (rosbridge)</Text>
            <View style={styles.row}>
              <TextInput
                style={[styles.input, { flex: 1 }]}
                value={host}
                onChangeText={setHost}
                placeholder="192.168.1.20"
                placeholderTextColor={colors.muted}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType={Platform.OS === 'ios' ? 'numbers-and-punctuation' : 'default'}
              />
              <TextInput
                style={[styles.input, { width: 72 }]}
                value={port}
                onChangeText={setPort}
                keyboardType="number-pad"
                placeholder="9090"
                placeholderTextColor={colors.muted}
              />
              <Pressable
                style={[styles.button, connected || conn === 'connecting' ? styles.buttonGhost : null]}
                onPress={connected || conn === 'connecting' ? () => { disconnect(); setConn('idle'); } : connect}
              >
                <Text style={styles.buttonText}>{connected || conn === 'connecting' ? 'Stop' : 'Connect'}</Text>
              </Pressable>
            </View>
            {conn === 'error' && connErr ? <Text style={styles.error}>{connErr}</Text> : null}

            <View style={[styles.row, { marginTop: 12 }]}>
              <Segment
                options={[
                  ['stream', 'Send this camera'],
                  ['watch', 'Watch only'],
                ]}
                value={mode}
                onChange={(v) => setMode(v as Mode)}
              />
            </View>
          </View>

          <View style={styles.viewer}>
            {frame ? (
              <Image source={{ uri: frame }} style={StyleSheet.absoluteFill} contentFit="contain" transition={0} />
            ) : (
              <View style={styles.placeholder}>
                <Text style={styles.placeholderText}>
                  {!connected
                    ? 'Connect to see the processed feed'
                    : mode === 'stream'
                      ? 'Waiting for processed frames…'
                      : 'Waiting for a camera to stream to ROS…'}
                </Text>
              </View>
            )}

            {needCamera && permission?.granted ? (
              <View style={styles.pip}>
                <CameraView
                  ref={camRef}
                  style={StyleSheet.absoluteFill}
                  facing={facing}
                  pictureSize={pictureSize}
                  animateShutter={false}
                  onCameraReady={onCameraReady}
                  onMountError={(e) => setConnErr(`Camera: ${e.message}`)}
                />
                <Pressable
                  style={styles.flip}
                  onPress={() => setFacing((f) => (f === 'back' ? 'front' : 'back'))}
                >
                  <Text style={styles.flipText}>⟲</Text>
                </Pressable>
              </View>
            ) : null}

            {needCamera && permission && !permission.granted ? (
              <Pressable style={styles.permission} onPress={requestPermission}>
                <Text style={styles.buttonText}>Allow camera</Text>
              </Pressable>
            ) : null}
          </View>

          <View style={styles.card}>
            <Text style={styles.label}>Overlays</Text>
            <View style={[styles.row, { flexWrap: 'wrap' }]}>
              <Toggle label="Boxes" on={overlay.boxes} onPress={() => setOverlay((o) => ({ ...o, boxes: !o.boxes }))} />
              <Toggle label="Hand skeleton" on={overlay.skeleton} onPress={() => setOverlay((o) => ({ ...o, skeleton: !o.skeleton }))} />
              <Toggle label="Motion heatmap" on={overlay.heatmap} onPress={() => setOverlay((o) => ({ ...o, heatmap: !o.heatmap }))} />
            </View>
          </View>

          <View style={styles.statsRow}>
            <Stat label="Processed" value={stats ? `${stats.fps.toFixed(1)} fps` : '–'} />
            <Stat label="Sending" value={mode === 'stream' ? `${sentFps.toFixed(1)} fps` : 'off'} />
            <Stat label="Motion" value={stats ? `${(stats.motion_level * 100).toFixed(1)}%` : '–'} />
            <Stat label="Hands" value={stats ? String(stats.hands.length) : '–'} />
          </View>

          {stats?.hands.length ? (
            <View style={[styles.row, { flexWrap: 'wrap', marginTop: 4 }]}>
              {stats.hands.map((h, i) => (
                <View key={i} style={styles.gesture}>
                  <Text style={styles.gestureText}>
                    {h.handedness} · {h.gesture.replace(/_/g, ' ')} · {h.fingers}☝
                  </Text>
                </View>
              ))}
            </View>
          ) : null}

          {stats && stats.source && stats.source !== DEVICE_ID ? (
            <Text style={styles.hint}>Showing frames from: {stats.source}</Text>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function KeepAwake() {
  useKeepAwake();
  return null;
}

function Segment({ options, value, onChange }: { options: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <View style={styles.segment}>
      {options.map(([v, label]) => (
        <Pressable key={v} style={[styles.segItem, value === v && styles.segItemOn]} onPress={() => onChange(v)}>
          <Text style={[styles.segText, value === v && styles.segTextOn]}>{label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function Toggle({ label, on, onPress }: { label: string; on: boolean; onPress: () => void }) {
  return (
    <Pressable style={[styles.chip, on && styles.chipOn]} onPress={onPress}>
      <Text style={[styles.chipText, on && styles.chipTextOn]}>{on ? '● ' : '○ '}{label}</Text>
    </Pressable>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function dotColor(s: ConnState) {
  return s === 'connected' ? colors.ok : s === 'connecting' ? colors.warn : s === 'error' ? colors.bad : colors.muted;
}

function statusLabel(s: ConnState) {
  return { idle: 'Offline', connecting: 'Connecting…', connected: 'Connected', error: 'Retrying…' }[s];
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: 16, gap: 12, maxWidth: 820, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: { color: colors.text, fontSize: 24, fontWeight: '700' },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.card, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { color: colors.text, fontSize: 13 },
  card: { backgroundColor: colors.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: colors.border },
  label: { color: colors.muted, fontSize: 12, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  input: { backgroundColor: colors.bg, color: colors.text, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16, borderWidth: 1, borderColor: colors.border },
  button: { backgroundColor: colors.accent, paddingHorizontal: 16, paddingVertical: 11, borderRadius: 10 },
  buttonGhost: { backgroundColor: colors.border },
  buttonText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  error: { color: colors.bad, marginTop: 8, fontSize: 13 },
  segment: { flexDirection: 'row', flex: 1, backgroundColor: colors.bg, borderRadius: 10, padding: 3 },
  segItem: { flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center' },
  segItemOn: { backgroundColor: colors.border },
  segText: { color: colors.muted, fontWeight: '600' },
  segTextOn: { color: colors.text },
  viewer: { aspectRatio: 3 / 4, maxHeight: 640, width: '100%', backgroundColor: '#000', borderRadius: 14, overflow: 'hidden', alignSelf: 'center' },
  placeholder: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },
  placeholderText: { color: colors.muted, textAlign: 'center' },
  pip: { position: 'absolute', right: 10, bottom: 10, width: 96, height: 128, borderRadius: 10, overflow: 'hidden', borderWidth: 2, borderColor: colors.accent, backgroundColor: '#111' },
  flip: { position: 'absolute', top: 4, right: 4, backgroundColor: '#0008', borderRadius: 12, width: 24, height: 24, alignItems: 'center', justifyContent: 'center' },
  flipText: { color: '#fff', fontSize: 14 },
  permission: { position: 'absolute', right: 10, bottom: 10, backgroundColor: colors.accent, padding: 10, borderRadius: 10 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border },
  chipOn: { backgroundColor: colors.accentSoft, borderColor: colors.accent },
  chipText: { color: colors.muted, fontWeight: '600' },
  chipTextOn: { color: colors.text },
  statsRow: { flexDirection: 'row', gap: 8 },
  stat: { flex: 1, backgroundColor: colors.card, borderRadius: 12, paddingVertical: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.border },
  statValue: { color: colors.text, fontSize: 16, fontWeight: '700' },
  statLabel: { color: colors.muted, fontSize: 11, marginTop: 2 },
  gesture: { backgroundColor: colors.card, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1, borderColor: colors.ok },
  gestureText: { color: colors.text, fontSize: 13 },
  hint: { color: colors.muted, fontSize: 12, textAlign: 'center' },
});
