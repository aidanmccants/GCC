import json, math, sys, random, base64
import numpy as np
from PIL import Image, ImageFilter
S = sys.argv[1]; OUT = sys.argv[2]
random.seed(7); np.random.seed(7)
S_LAT, N_LAT, W_LON, E_LON = 41.1495, 41.1610, -80.0900, -80.0705
LAT0, LON0 = (S_LAT + N_LAT) / 2, (W_LON + E_LON) / 2
KX = 111320 * math.cos(math.radians(LAT0)); KZ = 110574
def xz(lat, lon): return ((lon - LON0) * KX, -(lat - LAT0) * KZ)
W = (E_LON - W_LON) * KX; H = (N_LAT - S_LAT) * KZ
def merc(lat, lon, z):
    n = 2 ** z; return (lon + 180) / 360 * n * 256, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * 256
def local_to_ll(x, z): return LAT0 - z / KZ, LON0 + x / KX

# ---------- elevation ----------
dem = np.asarray(Image.open(f'{S}/dem.png').convert('RGB')).astype(np.float64)
E = dem[..., 0] * 256 + dem[..., 1] + dem[..., 2] / 256 - 32768
dx0, dy0 = merc(N_LAT, W_LON, 15)
def demsample(lat, lon):
    px, py = merc(lat, lon, 15); px -= dx0; py -= dy0
    px = min(max(px - .5, 0), E.shape[1] - 1.001); py = min(max(py - .5, 0), E.shape[0] - 1.001)
    i, j = int(py), int(px); fy, fx = py - i, px - j
    return (E[i, j] * (1 - fx) * (1 - fy) + E[i, j + 1] * fx * (1 - fy) + E[i + 1, j] * (1 - fx) * fy + E[i + 1, j + 1] * fx * fy)
STEP = 4.0
NX = int(W / STEP) + 1; NZ = int(H / STEP) + 1
hm = np.zeros((NZ, NX))
for r in range(NZ):
    for c in range(NX):
        x = -W / 2 + c * STEP; z = -H / 2 + r * STEP
        hm[r, c] = demsample(*local_to_ll(x, z))
# smooth a bit (box blur 3x3 twice)
def blur(a, n=1):
    for _ in range(n):
        p = np.pad(a, 1, mode='edge')
        a = sum(p[1 + dy:1 + dy + a.shape[0], 1 + dx:1 + dx + a.shape[1]] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9
    return a
hm = blur(hm, 2)
BASE = float(hm.min()) - 5

# ---------- geometry helpers ----------
def area(p):
    return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))
def clean(p, tol=0.35):
    if len(p) > 1 and abs(p[0][0] - p[-1][0]) < 1e-6 and abs(p[0][1] - p[-1][1]) < 1e-6: p = p[:-1]
    changed = True
    while changed and len(p) > 3:
        changed = False
        for i in range(len(p)):
            a, b, c = p[i - 1], p[i], p[(i + 1) % len(p)]
            ab = math.hypot(b[0] - a[0], b[1] - a[1])
            cr = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            ac = math.hypot(c[0] - a[0], c[1] - a[1]) or 1e-9
            if ab < tol or cr / ac < 0.12:
                p = p[:i] + p[i + 1:]; changed = True; break
    return p
def pip(x, z, poly):
    ins = False; n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]; x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1: ins = not ins
    return ins
def pip_np(X, Z, poly):
    ins = np.zeros(X.shape, bool); n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]; x2, z2 = poly[(i + 1) % n]
        cond = (z1 > Z) != (z2 > Z)
        with np.errstate(divide='ignore', invalid='ignore'):
            xi = (x2 - x1) * (Z - z1) / ((z2 - z1) if z2 != z1 else 1e-12) + x1
        ins ^= cond & (X < xi)
    return ins
def segdist(px, pz, a, b):
    vx, vz = b[0] - a[0], b[1] - a[1]; L2 = vx * vx + vz * vz or 1e-9
    t = max(0, min(1, ((px - a[0]) * vx + (pz - a[1]) * vz) / L2))
    return math.hypot(px - a[0] - t * vx, pz - a[1] - t * vz), t
def hsample(x, z):
    c = (x + W / 2) / STEP; r = (z + H / 2) / STEP
    c = min(max(c, 0), NX - 1.001); r = min(max(r, 0), NZ - 1.001)
    i, j = int(r), int(c); fy, fx = r - i, c - j
    return hm[i, j] * (1 - fx) * (1 - fy) + hm[i, j + 1] * fx * (1 - fy) + hm[i + 1, j] * (1 - fx) * fy + hm[i + 1, j + 1] * fx * fy
R1 = lambda v: round(v, 1)

D = json.load(open(f'{S}/osm/all.json'))
els = D['elements']
def ways_of(e):
    if e['type'] == 'way': return [('outer', e['geometry'])]
    if e['type'] == 'relation': return [(m.get('role') or 'outer', m['geometry']) for m in e['members'] if 'geometry' in m]
    return []
def joinrings(parts):
    """stitch open ways of a multipolygon into closed rings"""
    rings = []; segs = [list(p) for p in parts]
    while segs:
        cur = segs.pop(0)
        while abs(cur[0][0] - cur[-1][0]) + abs(cur[0][1] - cur[-1][1]) > 1e-3:
            for k, s in enumerate(segs):
                if abs(s[0][0] - cur[-1][0]) + abs(s[0][1] - cur[-1][1]) < 1e-3: cur += s[1:]; segs.pop(k); break
                if abs(s[-1][0] - cur[-1][0]) + abs(s[-1][1] - cur[-1][1]) < 1e-3: cur += s[::-1][1:]; segs.pop(k); break
            else: break
        rings.append(cur)
    return rings
def polys_of(e):
    """returns list of (outer, [holes]) in local coords"""
    parts = ways_of(e)
    outs = joinrings([[xz(p['lat'], p['lon']) for p in g] for role, g in parts if role == 'outer'])
    inns = joinrings([[xz(p['lat'], p['lon']) for p in g] for role, g in parts if role == 'inner'])
    res = []
    for o in outs:
        hs = [h for h in inns if pip(h[0][0], h[0][1], o)]
        res.append((o, hs))
    return res

# ---------- satellite (roof colours) ----------
sat = np.asarray(Image.open(f'{S}/sat.png').convert('RGB')).astype(np.float32)
sx0, sy0 = merc(N_LAT, W_LON, 18)
canopy = np.load(f'{S}/canopy.npy')
def satpx(x, z):
    lat, lon = local_to_ll(x, z); px, py = merc(lat, lon, 18); return px - sx0, py - sy0
def roofcolor(outer):
    xs = [p[0] for p in outer]; zs = [p[1] for p in outer]
    X, Z = np.meshgrid(np.arange(min(xs), max(xs), 0.8), np.arange(min(zs), max(zs), 0.8))
    m = pip_np(X, Z, outer)
    pts = list(zip(X[m], Z[m]))
    # keep points away from the edges
    pts = [p for p in pts if min(segdist(p[0], p[1], outer[i], outer[(i + 1) % len(outer)])[0] for i in range(len(outer))) > 1.6]
    if len(pts) < 4: return None
    cols = []
    for x, z in pts[::max(1, len(pts) // 400)]:
        px, py = satpx(x, z)
        if 0 <= int(py) < sat.shape[0] and 0 <= int(px) < sat.shape[1]: cols.append(sat[int(py), int(px)])
    if not cols: return None
    c = np.median(np.array(cols), axis=0)
    return '#%02x%02x%02x' % tuple(int(min(255, v)) for v in c)

# ---------- campus building specs ----------
# levels, roof type (hip/flat/gable), wall material, explicit roof colour (None = from satellite), pitch deg
BRICK, STONE, LBRICK, TAN = '#9b4a36', '#a49d8c', '#b0714f', '#c7b494'
SPEC = {
 'Harbison Chapel': dict(h=13, roof='hip', wall=STONE, rc='#585c60', pitch=55),
 'Crawford Hall': dict(h=14, roof='hip', wall=STONE, rc='#4c4f55', pitch=22),
 'Rockwell Hall of Science': dict(lv=4, roof='hip', wall=BRICK, pitch=30),
 'STEM Hall': dict(lv=4, roof='hip', wall=LBRICK, pitch=30),
 'Hoyt Hall of Engineering': dict(lv=3, roof='hip', wall=BRICK, pitch=30),
 'Henry Buhl Library': dict(lv=3, roof='flat', wall=BRICK),
 'Weir C. Ketler Technological Learning Center': dict(lv=3, roof='flat', wall=BRICK),
 'J. Howard Pew Fine Arts Center': dict(h=13, roof='flat', wall=BRICK),
 'Mary Anderson Pew Hall': dict(lv=4, roof='hip', wall=BRICK, pitch=32),
 'Mary Ethel Pew Hall': dict(lv=4, roof='hip', wall=BRICK, pitch=32),
 'Helen Harker Hall': dict(lv=4, roof='hip', wall=BRICK, pitch=32),
 'Hopeman Hall': dict(lv=4, roof='hip', wall=BRICK, pitch=30),
 'Hicks Hall': dict(lv=3, roof='hip', wall=BRICK, pitch=32),
 'Hicks Dining Hall': dict(h=6, roof='flat', wall=BRICK),
 'Lincoln Hall': dict(lv=3, roof='hip', wall=BRICK, pitch=32),
 'Memorial Hall': dict(lv=3, roof='hip', wall=BRICK, pitch=32),
 'Isaac C. Ketler Hall': dict(lv=4, roof='hip', wall=BRICK, pitch=32),
 'Ketler Recreation Center': dict(lv=2, roof='flat', wall=BRICK),
 'Breen Student Union': dict(lv=2, roof='hip', wall=BRICK, pitch=30),
 'Hall of Arts and Letters': dict(lv=3, roof='hip', wall=BRICK, pitch=30),
 'Physical Learning Center': dict(h=14, roof='flat', wall=LBRICK),
 'Physical Plant': dict(lv=2, roof='flat', wall=BRICK),
 'Zerbe Health Center': dict(lv=1, roof='hip', wall=BRICK, pitch=28),
 'Phillips Field House': dict(h=8, roof='hip', wall=BRICK, pitch=22),
 'Cunningham Hall': dict(lv=2, roof='hip', wall=BRICK, pitch=30),
 "President's House": dict(lv=2, roof='hip', wall=BRICK, pitch=35),
 'Carnegie Alumni Center': dict(lv=3, roof='hip', wall=BRICK, pitch=32),
 'Colonial Hall Apartments': dict(lv=3, roof='hip', wall=BRICK, pitch=28),
 'Rathburn Hall': dict(lv=2, roof='hip', wall=BRICK, pitch=32),
}
LEVEL_H = 3.8
campus_poly = None
for e in els:
    if e.get('tags', {}).get('amenity') == 'college' and e['type'] == 'way' and e['tags'].get('name') == 'Grove City College':
        campus_poly = clean([xz(p['lat'], p['lon']) for p in e['geometry']], 0.1)

buildings = []; bpolys = []
HOUSE_COLS = ['#e8e4da', '#d9d2c3', '#c9d1d6', '#e3d9b5', '#bfc7b2', '#d8c3a5', '#f0efe9', '#b9a58c', '#a7b6c2', '#cfa98c']
HOUSE_ROOF = ['#4a4a4f', '#5a524b', '#3e4248', '#6b5a4c', '#45403b']
# candidate footprints: OSM first, then Microsoft ML footprints that OSM is missing
cands = []
for e in els:
    t = e.get('tags', {})
    if 'building' not in t or e['type'] == 'node': continue
    for outer, holes in polys_of(e): cands.append((outer, holes, dict(t), e['id']))
try:
    ms = json.load(open(f'{S}/ms/ms_bbox.json'))
except FileNotFoundError:
    ms = []
added = 0
for k, m in enumerate(ms):
    poly = [xz(p[1], p[0]) for p in m['c']]
    if len(poly) > 1 and poly[0] == poly[-1]: poly = poly[:-1]
    mx = sum(p[0] for p in poly) / len(poly); mz = sum(p[1] for p in poly) / len(poly)
    dup = False
    for outer, holes, t, _ in cands:
        if t.get('building') == 'ms': continue
        ox = sum(p[0] for p in outer) / len(outer); oz = sum(p[1] for p in outer) / len(outer)
        if abs(ox - mx) > 120 or abs(oz - mz) > 120: continue
        if pip(mx, mz, outer) or pip(ox, oz, poly) or any(pip(p[0], p[1], outer) for p in poly):
            dup = True
            if m.get('h') and m['h'] > 0: t['ms_h'] = max(t.get('ms_h', 0), m['h'])
    if not dup:
        cands.append((poly, [], {'building': 'ms', 'ms_h': m.get('h') or -1}, 9_000_000_000 + k)); added += 1
print('microsoft footprints added', added)
for outer, holes, t, eid in cands:
    e = {'id': eid}
    if True:
        outer = clean(outer); holes = [clean(h) for h in holes]
        holes = [h for h in holes if len(h) >= 3 and abs(area(h)) > 4]
        if len(outer) < 3 or abs(area(outer)) < 6: continue
        if area(outer) < 0: outer = outer[::-1]          # CCW in x/z (z south) => we just need consistency
        holes = [h if area(h) < 0 else h[::-1] for h in holes]
        name = t.get('name', ''); bt = t.get('building')
        sp = SPEC.get(name)
        A = abs(area(outer))
        cx = sum(p[0] for p in outer) / len(outer); cz = sum(p[1] for p in outer) / len(outer)
        on_campus = campus_poly is not None and pip(cx, cz, campus_poly)
        rng = random.Random(e['id'])
        rc = roofcolor(outer)
        if sp:
            ht = sp.get('h') or sp['lv'] * LEVEL_H + 0.8
            roof = sp['roof']; wall = sp['wall']; rc = sp.get('rc') or rc; pitch = sp.get('pitch', 30); kind = 'stone' if wall == STONE else 'brick'
        else:
            lv = t.get('building:levels')
            lv = float(lv) if lv and lv.replace('.', '').isdigit() else None
            mh = t.get('ms_h', -1)
            if bt in ('house', 'residential', 'detached') or (bt in ('yes', 'ms') and A < 260 and not on_campus):
                # Street View: mostly 2-storey frame houses with front gables
                ht = (lv * 3.0 + 0.4) if lv else (min(6.4, max(3.2, mh * 0.7)) if mh > 0 else rng.choice([5.6, 6.0, 6.2])); roof = 'gable'; pitch = rng.choice([35, 40, 45])
                wall = rng.choice(HOUSE_COLS); rc = rng.choice(HOUSE_ROOF); kind = 'siding'
                if A < 45: ht = 3.0; pitch = 25; kind = 'plain'
            elif bt in ('garage', 'shed', 'garages') or A < 45:
                ht = 3.0; roof = 'gable'; pitch = 22; wall = rng.choice(HOUSE_COLS); rc = rng.choice(HOUSE_ROOF); kind = 'plain'
            else:
                ht = (lv * 4.0) if lv else (mh if mh > 2.5 else (2 if A < 1500 else 1.5) * 4.0); roof = 'flat'; pitch = 0
                wall = rng.choice(['#9b5a45', '#a9a39a', '#b8a58a', '#8f4c3c', '#c9c2b6']); kind = 'commercial' if not on_campus else 'brick'
                if t.get('roof:shape') == 'gabled' or t.get('roof:shape') == 'hipped': roof = 'hip'; pitch = 25
                if rc is None: rc = '#555555'
        if rc is None: rc = '#6b4a3a'
        # terrain base
        hs = [hsample(p[0], p[1]) for p in outer] + [hsample(cx, cz)]
        base = min(hs) - 0.6; ground = sum(hs) / len(hs)
        top = max(ground, min(hs) + 0.5) + ht
        b = dict(p=[[R1(x), R1(z)] for x, z in outer], b=R1(base - BASE), t=R1(top - BASE), r=roof, w=wall, c=rc, k=kind)
        if holes: b['h'] = [[[R1(x), R1(z)] for x, z in hh] for hh in holes]
        if pitch: b['pi'] = pitch
        if name: b['n'] = name
        if t.get('amenity') and not name: pass
        buildings.append(b); bpolys.append((outer, top - BASE, name))

# ---------- doors: footway endpoints that touch a building wall ----------
foot_nodes = []
for e in els:
    t = e.get('tags', {})
    if e['type'] == 'way' and t.get('highway') in ('footway', 'path', 'steps', 'pedestrian', 'service'):
        g = e['geometry']
        for p in (g[0], g[-1]) + tuple(g[1:-1]): foot_nodes.append(xz(p['lat'], p['lon']))
doors = []
for bi, (outer, top, name) in enumerate(bpolys):
    if not buildings[bi]['k'] in ('brick', 'stone', 'commercial'): continue
    found = []
    for fx, fz in foot_nodes:
        best = None
        for i in range(len(outer)):
            a, b = outer[i], outer[(i + 1) % len(outer)]
            d, tt = segdist(fx, fz, a, b)
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if d < 2.6 and L > 3 and 0.08 < tt < 0.92 and (best is None or d < best[0]): best = (d, i, tt)
        if best:
            d, i, tt = best; a, b = outer[i], outer[(i + 1) % len(outer)]
            px, pz = a[0] + (b[0] - a[0]) * tt, a[1] + (b[1] - a[1]) * tt
            if all(math.hypot(px - q[0], pz - q[1]) > 6 for q in found):
                ang = math.atan2(b[1] - a[1], b[0] - a[0])
                found.append((px, pz)); doors.append([R1(px), R1(pz), round(ang, 3), R1(hsample(px, pz) - BASE)])

# ---------- areas & lines ----------
areas = []; lines = []; trees = []
def ring_list(e):
    return [[[R1(x), R1(z)] for x, z in o] for o, hs in polys_of(e)]
excl = []  # polygons where trees must not stand
for e in els:
    t = e.get('tags', {})
    if e['type'] == 'node':
        if t.get('natural') == 'tree':
            x, z = xz(e['lat'], e['lon']); trees.append([R1(x), R1(z), 0])
        continue
    kind = None
    if t.get('natural') == 'water' or t.get('waterway') == 'riverbank': kind = 'water'
    elif t.get('leisure') == 'track': kind = 'track'
    elif t.get('leisure') == 'pitch': kind = 'pitch:' + (t.get('sport') or '').split(';')[0] + ':' + (t.get('surface') or '')
    elif t.get('leisure') == 'bleachers': kind = 'bleachers'
    elif t.get('amenity') == 'parking': kind = 'parking'
    elif t.get('natural') == 'wood': kind = 'wood'
    elif t.get('leisure') in ('park', 'playground'): kind = t['leisure']
    elif t.get('landuse') in ('grass', 'recreation_ground'): kind = 'grass'
    elif t.get('landuse') == 'retail': kind = 'retail'
    if kind and 'highway' not in t:
        for o, hs in polys_of(e):
            if len(o) < 3: continue
            if e['type'] == 'way' and abs(o[0][0] - o[-1][0]) + abs(o[0][1] - o[-1][1]) > 0.5: continue
            a = dict(k=kind, p=[[R1(x), R1(z)] for x, z in o])
            if kind.startswith('pitch') or kind == 'track':
                c = roofcolor(o)
                if c: a['c'] = c
            areas.append(a)
            if kind in ('water', 'track', 'parking', 'bleachers') or kind.startswith('pitch'): excl.append(o)
        continue
    hw = t.get('highway'); rw = t.get('railway'); ww = t.get('waterway'); br = t.get('barrier')
    if e['type'] != 'way': continue
    pts = [xz(p['lat'], p['lon']) for p in e['geometry']]
    if hw:
        if t.get('area') == 'yes': continue
        widths = dict(primary=11, secondary=10, tertiary=9, residential=7, unclassified=6.5, service=4.5, footway=2.6, pedestrian=4, path=1.8, steps=2.6, cycleway=2.5, track=3)
        w = widths.get(hw, 4)
        if hw == 'service' and t.get('service') in ('parking_aisle',): w = 6
        if t.get('footway') == 'sidewalk': w = 1.8
        L = dict(k=hw, w=w, p=[[R1(x), R1(z)] for x, z in pts])
        if t.get('surface'): L['s'] = t['surface']
        if t.get('bridge') == 'yes': L['br'] = 1
        if t.get('tunnel') == 'yes' or t.get('layer') == '-1': L['tu'] = 1
        if t.get('name'): L['n'] = t['name']
        lines.append(L)
    elif rw: lines.append(dict(k='rail', w=3, p=[[R1(x), R1(z)] for x, z in pts]))
    elif ww: lines.append(dict(k='stream', w=6, p=[[R1(x), R1(z)] for x, z in pts]))
    elif br in ('fence', 'wall'): lines.append(dict(k=br, w=0.2, p=[[R1(x), R1(z)] for x, z in pts]))

# lower terrain inside water polygons -> creek bed
for a in areas:
    if a['k'] == 'water':
        o = a['p']
        X, Z = np.meshgrid(-W / 2 + np.arange(NX) * STEP, -H / 2 + np.arange(NZ) * STEP)
        m = pip_np(X, Z, o)
        # widen mask by one cell so banks slope
        mm = m.copy(); mm[1:] |= m[:-1]; mm[:-1] |= m[1:]; mm[:, 1:] |= m[:, :-1]; mm[:, :-1] |= m[:, 1:]
        hm[mm] -= 1.0; hm[m] -= 1.3
        a['y'] = None

# ---------- trees from canopy ----------
def road_dist_ok(x, z, segs):
    for (a, b, w) in segs:
        if segdist(x, z, a, b)[0] < w / 2 + 1.0: return False
    return True
# spatial grid of road segments
GRID = 25; seggrid = {}
for L in lines:
    if L['k'] in ('footway', 'path', 'steps') and L['w'] < 3: ww = L['w'] - 1.0
    else: ww = L['w']
    if L['k'] in ('fence', 'wall', 'stream'): continue
    p = L['p']
    for i in range(len(p) - 1):
        a, b = p[i], p[i + 1]
        for gx in range(int(min(a[0], b[0]) // GRID) - 1, int(max(a[0], b[0]) // GRID) + 2):
            for gz in range(int(min(a[1], b[1]) // GRID) - 1, int(max(a[1], b[1]) // GRID) + 2):
                seggrid.setdefault((gx, gz), []).append((a, b, ww))
polygrid = {}
def addpoly(o, pad):
    xs = [q[0] for q in o]; zs = [q[1] for q in o]
    for gx in range(int(min(xs) // GRID) - 1, int(max(xs) // GRID) + 2):
        for gz in range(int(min(zs) // GRID) - 1, int(max(zs) // GRID) + 2):
            polygrid.setdefault((gx, gz), []).append((o, pad))
for o, top, n in bpolys: addpoly(o, 2.5)
for o in excl: addpoly(o, 3.0)
def free(x, z):
    k = (int(x // GRID), int(z // GRID))
    for o, pad in polygrid.get(k, []):
        if pip(x, z, o): return False
        if pad and min(segdist(x, z, o[i], o[(i + 1) % len(o)])[0] for i in range(len(o))) < pad: return False
    return road_dist_ok(x, z, seggrid.get(k, []))
trees = [t for t in trees if free(t[0], t[1])]
# Street View showed the canopy pass over-planting lawns, so require the whole 5 m patch
# around a candidate to read as canopy, and space candidates further apart
SP = 8.5
def is_canopy(x, z):
    px, py = satpx(x, z)
    return 0 <= int(py) < canopy.shape[0] and 0 <= int(px) < canopy.shape[1] and canopy[int(py), int(px)]
for gz in np.arange(-H / 2 + 3, H / 2 - 3, SP):
    for gx in np.arange(-W / 2 + 3, W / 2 - 3, SP):
        x = gx + random.uniform(-2.5, 2.5); z = gz + random.uniform(-2.5, 2.5)
        if not all(is_canopy(x + ox, z + oz) for ox, oz in ((0, 0), (2.5, 0), (-2.5, 0), (0, 2.5), (0, -2.5))): continue
        if any(abs(t[0] - x) < 3 and abs(t[1] - z) < 3 for t in trees[-40:]): continue
        if not free(x, z): continue
        trees.append([R1(x), R1(z), random.randint(1, 3)])
for t in trees: t.append(R1(hsample(t[0], t[1]) - BASE))

# ---------- lamps along campus footways ----------
lamps = []
for L in lines:
    if L['k'] not in ('footway', 'pedestrian') or L.get('br'): continue
    p = L['p']; acc = 0
    for i in range(len(p) - 1):
        a, b = p[i], p[i + 1]; seg = math.hypot(b[0] - a[0], b[1] - a[1])
        while acc < seg:
            tt = acc / seg; x = a[0] + (b[0] - a[0]) * tt; z = a[1] + (b[1] - a[1]) * tt
            if campus_poly and pip(x, z, campus_poly):
                nx, nz = -(b[1] - a[1]) / seg, (b[0] - a[0]) / seg
                lx, lz = x + nx * (L['w'] / 2 + 0.5), z + nz * (L['w'] / 2 + 0.5)
                if free(lx, lz) or True: lamps.append([R1(lx), R1(lz), R1(hsample(lx, lz) - BASE)])
            acc += 28
        acc -= seg

# ---------- labels / special features ----------
def ll_px(px, py):
    # satellite pixel -> local
    n = 2 ** 18 * 256; X = (px + sx0) / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (py + sy0) / n))))
    return xz(lat, X)
specials = {
    'harbisonTower': ll_px(1703, 1057),
    'crawfordTower': ll_px(1572, 1260),
    'spawn': ll_px(1690, 1215),
}
specials = {k: [R1(v[0]), R1(v[1]), R1(hsample(*v) - BASE)] for k, v in specials.items()}
# entrance sign: start of Campus Drive
for L in lines:
    if L.get('n') == 'Campus Drive':
        p = L['p'][0]; specials['sign'] = [p[0], p[1], R1(hsample(*p) - BASE)]; break

# named businesses and churches (for storefront signs and church styling)
pois = []
try:
    for e in json.load(open(f'{S}/osm/shops.json'))['elements']:
        t = e.get('tags', {}); c = e.get('center', e)
        if 'name' not in t or 'lat' not in c: continue
        x, z = xz(c['lat'], c['lon'])
        if abs(x) < W / 2 and abs(z) < H / 2:
            pois.append(dict(n=t['name'], x=R1(x), z=R1(z), t=t.get('shop') or t.get('amenity') or t.get('office') or t.get('craft') or t.get('leisure') or ''))
except FileNotFoundError:
    pass
for e in els:
    t = e.get('tags', {})
    if e['type'] == 'node' and t.get('amenity') == 'place_of_worship' and t.get('name') and not any(p['n'] == t['name'] for p in pois):
        x, z = xz(e['lat'], e['lon']); pois.append(dict(n=t['name'], x=R1(x), z=R1(z), t='place_of_worship'))
print('pois', len(pois))

hq = np.round(np.clip(hm - BASE, 0, 6000) * 10).astype(np.uint16)
data = dict(W=R1(W), H=R1(H), step=STEP, nx=NX, nz=NZ, base=R1(BASE), lat0=LAT0, lon0=LON0,
            hm=base64.b64encode(hq.tobytes()).decode(), buildings=buildings, areas=areas, lines=lines,
            trees=trees, lamps=lamps, doors=doors, specials=specials, pois=pois,
            campus=[[R1(x), R1(z)] for x, z in campus_poly] if campus_poly else None)
s = json.dumps(data, separators=(',', ':'))
open(OUT, 'w').write('window.GCC_DATA=' + s + ';')
print('W,H', W, H, 'grid', NX, NZ, 'bytes', len(s))
print('buildings', len(buildings), 'areas', len(areas), 'lines', len(lines), 'trees', len(trees), 'lamps', len(lamps), 'doors', len(doors))
print(specials)
