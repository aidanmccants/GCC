// Groove City College, multiplayer. The Worker serves the map page and relays
// each visitor's position to everyone else through one Durable Object (the "room").
import PAGE from './page.html';

const MAX_PLAYERS = 40;     // one room; keeps the fan-out of position updates small
const MIN_MOVE_MS = 60;     // ignore position updates arriving faster than this from one visitor
// the campus is about 1634 x 1272 m, centred on 0,0 (same coordinates as the page)
const BOUNDS = { x: 900, z: 700, yMin: -50, yMax: 700 };

const ADJECTIVES = ['Brisk', 'Calm', 'Dapper', 'Eager', 'Fuzzy', 'Gentle', 'Hasty', 'Jolly', 'Keen', 'Lucky',
  'Merry', 'Nimble', 'Plucky', 'Quiet', 'Rapid', 'Sunny', 'Swift', 'Tidy', 'Vivid', 'Witty', 'Zesty',
  'Bold', 'Brave', 'Chill', 'Cosmic', 'Dizzy', 'Golden', 'Happy', 'Lively', 'Mellow', 'Peppy', 'Rustic',
  'Silly', 'Sleepy', 'Stout', 'Wacky'];
const NOUNS = ['Otter', 'Badger', 'Falcon', 'Beaver', 'Heron', 'Walrus', 'Panda', 'Lynx', 'Moose', 'Penguin',
  'Tiger', 'Koala', 'Gopher', 'Raven', 'Wombat', 'Pelican', 'Bison', 'Ferret', 'Hedgehog', 'Narwhal',
  'Quokka', 'Sloth', 'Yak', 'Owl', 'Fox', 'Hippo', 'Lemur', 'Gecko'];

const pick = list => list[Math.floor(Math.random() * list.length)];
// a number from the client, or null if it is missing or not finite; clamped to the allowed range
const num = (v, lo, hi) => (typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : null);

// Hibernating WebSocket room. Each socket's state (id, name, last position) lives in its
// attachment, so the room keeps working while Durable Object memory is evicted between messages.
export class MapRoom {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }

  async fetch(request) {
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('Expected a WebSocket upgrade', { status: 426 });
    }
    const [client, server] = Object.values(new WebSocketPair());
    const sockets = this.ctx.getWebSockets();
    this.ctx.acceptWebSocket(server);

    if (sockets.length >= MAX_PLAYERS) {
      server.send(JSON.stringify({ t: 'full' }));
      server.close(1013, 'room full');
      return new Response(null, { status: 101, webSocket: client });
    }

    const taken = new Set(sockets.map(s => s.deserializeAttachment()?.name));
    const me = { id: crypto.randomUUID().slice(0, 8), name: this.pickName(taken), x: null, y: null, z: null, yaw: 0, last: 0 };
    server.serializeAttachment(me);

    // players who have sent at least one position; the others appear once they move
    const players = sockets
      .map(s => s.deserializeAttachment())
      .filter(p => p && p.x !== null)
      .map(({ id, name, x, y, z, yaw }) => ({ id, name, x, y, z, yaw }));
    server.send(JSON.stringify({ t: 'welcome', id: me.id, name: me.name, players }));
    this.broadcast(JSON.stringify({ t: 'join', id: me.id, name: me.name }), server);

    return new Response(null, { status: 101, webSocket: client });
  }

  webSocketMessage(ws, message) {
    if (typeof message !== 'string' || message.length > 300) return;
    let m;
    try { m = JSON.parse(message); } catch { return; }
    const me = ws.deserializeAttachment();
    if (!me || m?.t !== 'move') return;

    const now = Date.now();
    if (now - me.last < MIN_MOVE_MS) return;
    const x = num(m.x, -BOUNDS.x, BOUNDS.x), y = num(m.y, BOUNDS.yMin, BOUNDS.yMax);
    const z = num(m.z, -BOUNDS.z, BOUNDS.z), yaw = num(m.yaw, -1e6, 1e6);
    if (x === null || y === null || z === null || yaw === null) return;

    Object.assign(me, { x, y, z, yaw, last: now });
    ws.serializeAttachment(me);
    this.broadcast(JSON.stringify({ t: 'move', id: me.id, x, y, z, yaw }), ws);
  }

  webSocketClose(ws, code, reason) {
    const me = ws.deserializeAttachment();
    if (me) this.broadcast(JSON.stringify({ t: 'leave', id: me.id }), ws);
    try { ws.close(code, reason); } catch { /* already closed */ }
  }

  webSocketError(ws) {
    this.webSocketClose(ws, 1011, 'error');
  }

  broadcast(msg, except) {
    for (const s of this.ctx.getWebSockets()) {
      if (s === except) continue;
      try { s.send(msg); } catch { /* socket is closing; its close handler will tell the room */ }
    }
  }

  pickName(taken) {
    for (let i = 0; i < 50; i++) {
      const name = pick(ADJECTIVES) + pick(NOUNS) + (10 + Math.floor(Math.random() * 90));
      if (!taken.has(name)) return name;
    }
    return pick(ADJECTIVES) + pick(NOUNS) + crypto.randomUUID().slice(0, 4);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/ws') {
      return env.ROOM.get(env.ROOM.idFromName('campus')).fetch(request);
    }
    if (url.pathname === '/' || url.pathname === '/index.html') {
      return new Response(PAGE, { headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-cache' } });
    }
    return new Response('Not found', { status: 404 });
  },
};
