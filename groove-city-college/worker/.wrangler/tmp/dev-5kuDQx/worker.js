var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/worker.js
import PAGE from "./404a90a6179b15f4558031e8e8d5d80ff658ee92-page.html";
var MAX_PLAYERS = 40;
var MIN_MOVE_MS = 60;
var BOUNDS = { x: 900, z: 700, yMin: -50, yMax: 700 };
var ADJECTIVES = [
  "Brisk",
  "Calm",
  "Dapper",
  "Eager",
  "Fuzzy",
  "Gentle",
  "Hasty",
  "Jolly",
  "Keen",
  "Lucky",
  "Merry",
  "Nimble",
  "Plucky",
  "Quiet",
  "Rapid",
  "Sunny",
  "Swift",
  "Tidy",
  "Vivid",
  "Witty",
  "Zesty",
  "Bold",
  "Brave",
  "Chill",
  "Cosmic",
  "Dizzy",
  "Golden",
  "Happy",
  "Lively",
  "Mellow",
  "Peppy",
  "Rustic",
  "Silly",
  "Sleepy",
  "Stout",
  "Wacky"
];
var NOUNS = [
  "Otter",
  "Badger",
  "Falcon",
  "Beaver",
  "Heron",
  "Walrus",
  "Panda",
  "Lynx",
  "Moose",
  "Penguin",
  "Tiger",
  "Koala",
  "Gopher",
  "Raven",
  "Wombat",
  "Pelican",
  "Bison",
  "Ferret",
  "Hedgehog",
  "Narwhal",
  "Quokka",
  "Sloth",
  "Yak",
  "Owl",
  "Fox",
  "Hippo",
  "Lemur",
  "Gecko"
];
var pick = /* @__PURE__ */ __name((list) => list[Math.floor(Math.random() * list.length)], "pick");
var num = /* @__PURE__ */ __name((v, lo, hi) => typeof v === "number" && Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : null, "num");
var MapRoom = class {
  static {
    __name(this, "MapRoom");
  }
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }
  async fetch(request) {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected a WebSocket upgrade", { status: 426 });
    }
    const [client, server] = Object.values(new WebSocketPair());
    const sockets = this.ctx.getWebSockets();
    this.ctx.acceptWebSocket(server);
    if (sockets.length >= MAX_PLAYERS) {
      server.send(JSON.stringify({ t: "full" }));
      server.close(1013, "room full");
      return new Response(null, { status: 101, webSocket: client });
    }
    const taken = new Set(sockets.map((s) => s.deserializeAttachment()?.name));
    const me = { id: crypto.randomUUID().slice(0, 8), name: this.pickName(taken), x: null, y: null, z: null, yaw: 0, last: 0 };
    server.serializeAttachment(me);
    const players = sockets.map((s) => s.deserializeAttachment()).filter((p) => p && p.x !== null).map(({ id, name, x, y, z, yaw }) => ({ id, name, x, y, z, yaw }));
    server.send(JSON.stringify({ t: "welcome", id: me.id, name: me.name, players }));
    this.broadcast(JSON.stringify({ t: "join", id: me.id, name: me.name }), server);
    return new Response(null, { status: 101, webSocket: client });
  }
  webSocketMessage(ws, message) {
    if (typeof message !== "string" || message.length > 300) return;
    let m;
    try {
      m = JSON.parse(message);
    } catch {
      return;
    }
    const me = ws.deserializeAttachment();
    if (!me || m?.t !== "move") return;
    const now = Date.now();
    if (now - me.last < MIN_MOVE_MS) return;
    const x = num(m.x, -BOUNDS.x, BOUNDS.x), y = num(m.y, BOUNDS.yMin, BOUNDS.yMax);
    const z = num(m.z, -BOUNDS.z, BOUNDS.z), yaw = num(m.yaw, -1e6, 1e6);
    if (x === null || y === null || z === null || yaw === null) return;
    Object.assign(me, { x, y, z, yaw, last: now });
    ws.serializeAttachment(me);
    this.broadcast(JSON.stringify({ t: "move", id: me.id, x, y, z, yaw }), ws);
  }
  webSocketClose(ws, code, reason) {
    const me = ws.deserializeAttachment();
    if (me) this.broadcast(JSON.stringify({ t: "leave", id: me.id }), ws);
    try {
      ws.close(code, reason);
    } catch {
    }
  }
  webSocketError(ws) {
    this.webSocketClose(ws, 1011, "error");
  }
  broadcast(msg, except) {
    for (const s of this.ctx.getWebSockets()) {
      if (s === except) continue;
      try {
        s.send(msg);
      } catch {
      }
    }
  }
  pickName(taken) {
    for (let i = 0; i < 50; i++) {
      const name = pick(ADJECTIVES) + pick(NOUNS) + (10 + Math.floor(Math.random() * 90));
      if (!taken.has(name)) return name;
    }
    return pick(ADJECTIVES) + pick(NOUNS) + crypto.randomUUID().slice(0, 4);
  }
};
var worker_default = {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/ws") {
      return env.ROOM.get(env.ROOM.idFromName("campus")).fetch(request);
    }
    if (url.pathname === "/" || url.pathname === "/index.html") {
      return new Response(PAGE, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-cache" } });
    }
    return new Response("Not found", { status: 404 });
  }
};

// node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// node_modules/wrangler/templates/middleware/middleware-miniflare3-json-error.ts
function reduceError(e) {
  return {
    name: e?.name,
    message: e?.message ?? String(e),
    stack: e?.stack,
    cause: e?.cause === void 0 ? void 0 : reduceError(e.cause)
  };
}
__name(reduceError, "reduceError");
var jsonError = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } catch (e) {
    const error = reduceError(e);
    const body = JSON.stringify(error);
    const headers = {
      "Content-Type": "application/json",
      "MF-Experimental-Error-Stack": "true"
    };
    const encoded = encodeURIComponent(body);
    if (encoded.length <= 8192) {
      headers["MF-Experimental-Error-Stack-Payload"] = encoded;
    }
    return new Response(body, { status: 500, headers });
  }
}, "jsonError");
var middleware_miniflare3_json_error_default = jsonError;

// .wrangler/tmp/bundle-oIlXkp/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default,
  middleware_miniflare3_json_error_default
];
var middleware_insertion_facade_default = worker_default;

// node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-oIlXkp/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class ___Facade_ScheduledController__ {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  scheduledTime;
  cron;
  static {
    __name(this, "__Facade_ScheduledController__");
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof ___Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
function wrapExportedHandler(worker) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = /* @__PURE__ */ __name((request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    }, "#fetchDispatcher");
    #dispatcher = /* @__PURE__ */ __name((type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    }, "#dispatcher");
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  MapRoom,
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=worker.js.map
