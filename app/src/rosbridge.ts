// Minimal rosbridge v2 client (JSON over WebSocket). Works the same in React Native and the browser.
// Protocol: https://github.com/RobotWebTools/rosbridge_suite/blob/ros2/ROSBRIDGE_PROTOCOL.md

export type ConnState = 'idle' | 'connecting' | 'connected' | 'error';

type Handler = (msg: any) => void;

interface Sub {
  type: string;
  handlers: Set<Handler>;
  opts: { throttle_rate?: number; queue_length?: number };
}

export class RosBridge {
  private ws: WebSocket | null = null;
  private subs = new Map<string, Sub>();
  private adverts = new Map<string, string>();
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private wantOpen = false;
  state: ConnState = 'idle';
  lastError = '';
  onState: (s: ConnState, err?: string) => void = () => {};

  constructor(public url: string) {}

  connect() {
    this.wantOpen = true;
    this.open();
  }

  close() {
    this.wantOpen = false;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.ws?.close();
    this.ws = null;
    this.setState('idle');
  }

  private setState(s: ConnState, err = '') {
    this.state = s;
    this.lastError = err;
    this.onState(s, err);
  }

  private open() {
    this.setState('connecting');
    let ws: WebSocket;
    try {
      ws = new WebSocket(this.url);
    } catch (e: any) {
      this.setState('error', String(e?.message ?? e));
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.setState('connected');
      // (Re)announce everything after a reconnect.
      this.adverts.forEach((type, topic) => this.send({ op: 'advertise', topic, type }));
      this.subs.forEach((s, topic) => this.sendSubscribe(topic, s));
    };
    ws.onmessage = (ev) => {
      let data: any;
      try {
        data = JSON.parse(typeof ev.data === 'string' ? ev.data : '');
      } catch {
        return;
      }
      if (data.op === 'publish') this.subs.get(data.topic)?.handlers.forEach((h) => h(data.msg));
    };
    ws.onerror = (ev: any) => {
      this.lastError = ev?.message ?? 'Connection failed';
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      if (!this.wantOpen) return;
      this.setState('error', this.lastError || 'Disconnected');
      this.retryTimer = setTimeout(() => this.wantOpen && this.open(), 2000);
    };
  }

  private send(obj: object) {
    if (this.ws && this.ws.readyState === 1) {
      this.ws.send(JSON.stringify(obj));
      return true;
    }
    return false;
  }

  private sendSubscribe(topic: string, s: Sub) {
    this.send({ op: 'subscribe', topic, type: s.type, ...s.opts });
  }

  /** Bytes queued but not yet sent (0 where the platform doesn't report it). Used to avoid flooding slow links. */
  get buffered(): number {
    return (this.ws as any)?.bufferedAmount ?? 0;
  }

  advertise(topic: string, type: string) {
    if (this.adverts.get(topic) === type) return;
    this.adverts.set(topic, type);
    this.send({ op: 'advertise', topic, type });
  }

  publish(topic: string, type: string, msg: object) {
    this.advertise(topic, type);
    return this.send({ op: 'publish', topic, msg });
  }

  subscribe(topic: string, type: string, handler: Handler, opts: Sub['opts'] = {}) {
    let s = this.subs.get(topic);
    if (!s) {
      s = { type, handlers: new Set(), opts };
      this.subs.set(topic, s);
      this.sendSubscribe(topic, s);
    }
    s.handlers.add(handler);
    return () => {
      const cur = this.subs.get(topic);
      if (!cur) return;
      cur.handlers.delete(handler);
      if (cur.handlers.size === 0) {
        this.subs.delete(topic);
        this.send({ op: 'unsubscribe', topic });
      }
    };
  }
}

export function stampNow() {
  const ms = Date.now();
  return { sec: Math.floor(ms / 1000), nanosec: (ms % 1000) * 1e6 };
}
