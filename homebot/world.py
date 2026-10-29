"""
Simulated house for the Cognibot demo: map, A* navigation, robot motion,
simulated camera perception, items, charging.

Coordinates in metres: x grows east, z grows south (y is up in the 3D view).
Heading th (radians): forward = (cos th, sin th), th=0 faces east, +pi/2 south.
"""
from __future__ import annotations

import heapq
import math
import threading
import time
from collections import deque

T = 0.12          # wall thickness
CELL = 0.1        # planning grid resolution
R_ROBOT = 0.30    # robot body radius
INFLATE = 0.36    # clearance kept from obstacles when planning
REACH = 1.25      # how far the robot can pick up / hand over
V_MAX, W_MAX = 0.75, 2.0
W, H = 14.0, 10.0


def hwall(z, x0, x1, gaps=()):
    out, cur = [], x0
    for a, b in sorted(gaps):
        out.append((cur, z - T / 2, a, z + T / 2))
        cur = b
    out.append((cur, z - T / 2, x1, z + T / 2))
    return out


def vwall(x, z0, z1, gaps=()):
    out, cur = [], z0
    for a, b in sorted(gaps):
        out.append((x - T / 2, cur, x + T / 2, a))
        cur = b
    out.append((x - T / 2, cur, x + T / 2, z1))
    return out


WALLS = (
    hwall(0, -T / 2, W + T / 2) + hwall(H, -T / 2, W + T / 2)
    + vwall(0, 0, H, [(4.25, 5.35)]) + vwall(W, 0, H)
    + hwall(4.0, 0, W, [(3.6, 4.8), (5.9, 7.1), (8.6, 9.8)])
    + vwall(5.0, 0, 4.0) + vwall(8.0, 0, 4.0)
    + hwall(5.6, 0, W, [(1.0, 3.2), (9.6, 10.8)])
    + vwall(8.5, 5.6, H, [(7.3, 8.6)])
)
FRONT_DOOR_RECT = (-T / 2, 4.25, T / 2, 5.35)

ROOMS = {
    "bedroom": ("Bedroom", (0, 0, 5, 4), (3.0, 2.3)),
    "bathroom": ("Bathroom", (5, 0, 8, 4), (6.4, 2.4)),
    "study": ("Study", (8, 0, 14, 4), (10.6, 2.3)),
    "hallway": ("Hallway", (0, 4, 14, 5.6), (7.0, 4.8)),
    "living_room": ("Living room", (0, 5.6, 8.5, 10), (4.0, 6.95)),
    "kitchen": ("Kitchen", (8.5, 5.6, 14, 10), (11.1, 6.6)),
}

# id: (type, rect, height, facing, friendly name). flat=True -> rug, not an obstacle
FURNITURE = {
    "bed": ("bed", (0.2, 0.15, 1.8, 2.2), 0.55, "s", "bed"),
    "bedside": ("table", (1.9, 0.15, 2.4, 0.6), 0.55, "s", "bedside table"),
    "wardrobe": ("wardrobe", (3.8, 0.12, 4.85, 0.75), 2.0, "s", "wardrobe"),
    "armchair": ("armchair", (0.4, 2.9, 1.2, 3.7), 0.85, "e", "armchair"),
    "bathtub": ("bathtub", (5.12, 0.12, 6.9, 0.95), 0.55, "s", "bathtub"),
    "toilet": ("toilet", (7.3, 0.12, 7.88, 0.75), 0.45, "s", "toilet"),
    "bath_sink": ("sink", (7.35, 1.6, 7.88, 2.5), 0.85, "w", "bathroom sink"),
    "desk": ("desk", (11.2, 0.15, 13.2, 0.85), 0.75, "s", "desk"),
    "desk_chair": ("chair", (11.9, 1.0, 12.5, 1.55), 0.9, "n", "desk chair"),
    "bookshelf": ("bookshelf", (13.5, 1.5, 13.88, 3.5), 1.9, "w", "bookshelf"),
    "plant_study": ("plant", (8.15, 0.15, 8.6, 0.6), 1.1, "s", "plant"),
    "console": ("table", (0.5, 4.08, 1.6, 4.45), 0.8, "s", "hallway table"),
    "dock": ("dock", (13.45, 4.45, 13.88, 5.15), 0.35, "w", "charging station"),
    "tv_stand": ("tvstand", (4.4, 5.75, 6.4, 6.15), 0.5, "s", "TV stand"),
    "sofa": ("sofa", (4.0, 8.9, 6.8, 9.88), 0.85, "n", "sofa"),
    "coffee_table": ("table", (4.7, 7.4, 6.1, 8.1), 0.42, "n", "coffee table"),
    "dining_table": ("table", (0.8, 7.6, 2.4, 8.8), 0.75, "n", "dining table"),
    "chair_n": ("chair", (1.3, 7.15, 1.9, 7.55), 0.9, "s", "chair"),
    "chair_s": ("chair", (1.3, 8.85, 1.9, 9.3), 0.9, "n", "chair"),
    "chair_w": ("chair", (0.3, 7.9, 0.75, 8.5), 0.9, "e", "chair"),
    "plant_living": ("plant", (7.75, 9.35, 8.3, 9.88), 1.2, "s", "plant"),
    "fridge": ("fridge", (8.62, 9.1, 9.4, 9.88), 1.9, "n", "fridge"),
    "counter_s": ("counter", (9.45, 9.3, 13.88, 9.88), 0.9, "n", "kitchen counter"),
    "counter_e": ("counter", (13.3, 6.2, 13.88, 9.3), 0.9, "w", "kitchen counter"),
    "island": ("counter", (10.3, 7.3, 11.9, 8.1), 0.92, "n", "kitchen island"),
    "rug_bed": ("rug", (2.0, 1.2, 3.6, 3.0), 0.0, "s", "rug"),
    "rug_living": ("rug", (4.3, 6.9, 6.6, 8.6), 0.0, "s", "rug"),
    "rug_hall": ("rug", (2.0, 4.5, 12.0, 5.1), 0.0, "s", "rug"),
}

# Navigation targets with a fixed approach pose (x, z, heading or None)
PLACES = {
    "charging_station": ("charging station", (13.05, 4.8, 0.0)),
    "front_door": ("front door", (0.9, 4.8, math.pi)),
    "stove": ("stove", (12.0, 8.75, math.pi / 2)),
    "fridge": ("fridge", (9.0, 8.4, math.pi / 2)),
    "kitchen_sink": ("kitchen sink", (10.2, 8.75, math.pi / 2)),
    "user": ("you, on the living-room sofa", (3.55, 9.35, 0.0)),
    "grandpa": ("Grandpa, in the bedroom armchair", (2.0, 3.3, math.pi)),
    "dining_table": ("dining table", (3.0, 8.2, math.pi)),
    "desk": ("study desk", (12.9, 1.45, -math.pi / 2)),
    "bookshelf": ("bookshelf", (12.9, 2.5, 0.0)),
    "tv": ("TV", (5.4, 7.0, -math.pi / 2)),
    "bathroom_sink": ("bathroom sink", (6.8, 2.05, 0.0)),
    "bed": ("bed", (2.6, 1.2, math.pi)),
}

PEOPLE = {"user": ("you", (4.45, 0.95, 9.35)), "grandpa": ("Grandpa", (0.8, 0.95, 3.3))}

ITEMS = {
    "water_bottle": ("bottle of water", (10.6, 0.92, 7.7)),
    "medicine": ("medicine box", (7.6, 0.85, 2.05)),
    "tv_remote": ("TV remote", (5.0, 0.42, 7.75)),
    "book": ("book", (12.8, 0.75, 0.55)),
    "keys": ("keys", (1.05, 0.8, 4.27)),
    "apple": ("apple", (2.15, 0.75, 8.2)),
}

APPLIANCES = {  # id: (name, position)
    "stove": ("stove", (12.0, 0.9, 9.6)),
    "milk_pot": ("milk pot", (12.0, 0.95, 9.55)),
    "tv": ("TV", (5.4, 1.0, 5.95)),
    "front_door": ("front door", (0.0, 1.0, 4.8)),
}

BOX_SPOTS = [(5.3, 4.5), (5.3, 5.1)]  # "block the hallway" scenario


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def rect_dist(px, pz, r):
    dx = max(r[0] - px, 0, px - r[2])
    dz = max(r[1] - pz, 0, pz - r[3])
    return math.hypot(dx, dz)


def ray_rect(ox, oz, dx, dz, r):
    """Distance along the ray (unit dir) to rect r, or None."""
    tmin, tmax = -1e9, 1e9
    for o, d, lo, hi in ((ox, dx, r[0], r[2]), (oz, dz, r[1], r[3])):
        if abs(d) < 1e-9:
            if o < lo or o > hi:
                return None
        else:
            t1, t2 = (lo - o) / d, (hi - o) / d
            tmin, tmax = max(tmin, min(t1, t2)), min(tmax, max(t1, t2))
    if tmax < max(tmin, 0):
        return None
    return max(tmin, 0)


def room_of(x, z):
    for rid, (_, r, _) in ROOMS.items():
        if r[0] <= x <= r[2] and r[1] <= z <= r[3]:
            return rid
    return "hallway"


class World:
    def __init__(self, time_scale: float = 1.0):
        self.lock = threading.RLock()
        self.time_scale = time_scale
        self.ev_id = 0
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        with self.lock:
            self.x, self.z, self.th = 13.05, 4.8, 0.0
            self.v = self.w = 0.0
            self.battery = 82.0
            self.mast = 0.0           # 0 lowered .. 1 raised (periscope camera)
            self.mast_target = 0.0
            self.activity = "idle"
            self.task = "Docked, charging"
            self.nav = None
            self.manual = None
            self.epoch = getattr(self, "epoch", 0) + 1
            self.boxes: list[tuple] = []
            self.obst_version = 0
            self.stove_on = True
            self.milk_temp = 70.0
            self.boil_time = 0.0
            self.boiled_over = False
            self.tv_on = True
            self.door_open = False
            self.items = {
                k: {"pos": list(p), "carried": False, "holder": None, "on": self._surface_at(p)}
                for k, (_, p) in ITEMS.items()
            }
            self.events = deque(maxlen=40)
            self.speech = {"id": 0, "text": ""}
            self.heard = {"id": 0, "text": ""}
            self.detections = []
            self.sonar = 2.0
            self.busy = False
            self._build_grid()
            self.event("World reset. Robot docked at the charging station.")

    def event(self, text, kind="info"):
        self.ev_id += 1
        self.events.append({"id": self.ev_id, "text": text, "kind": kind, "t": time.time()})

    def say(self, text):
        with self.lock:
            self.speech = {"id": self.speech["id"] + 1, "text": text}

    def set_heard(self, text):
        with self.lock:
            self.heard = {"id": self.heard["id"] + 1, "text": text}

    @property
    def docked(self):
        return math.hypot(self.x - 13.05, self.z - 4.8) < 0.15 and abs(wrap(self.th)) < 0.2

    def obstacles(self, tall_only=False):
        rects = list(WALLS)
        if not self.door_open:
            rects.append(FRONT_DOOR_RECT)
        for _, (typ, r, h, _, _) in FURNITURE.items():
            if typ == "rug":
                continue
            if tall_only and h < 1.4:
                continue
            rects.append(r)
        if not tall_only:
            rects += self.boxes
        return rects

    def _surface_at(self, p):
        for fid, (typ, r, h, _, name) in FURNITURE.items():
            if typ != "rug" and r[0] - 0.05 <= p[0] <= r[2] + 0.05 and r[1] - 0.05 <= p[2] <= r[3] + 0.05:
                return fid
        return None

    # ------------------------------------------------------------ planning
    def _build_grid(self):
        self.nx, self.nz = int(W / CELL), int(H / CELL)
        g = bytearray(self.nx * self.nz)
        for r in self.obstacles():
            i0 = max(0, int((r[0] - INFLATE) / CELL)); i1 = min(self.nx - 1, int((r[2] + INFLATE) / CELL))
            j0 = max(0, int((r[1] - INFLATE) / CELL)); j1 = min(self.nz - 1, int((r[3] + INFLATE) / CELL))
            for j in range(j0, j1 + 1):
                cz = (j + 0.5) * CELL
                for i in range(i0, i1 + 1):
                    if rect_dist((i + 0.5) * CELL, cz, r) <= INFLATE:
                        g[j * self.nx + i] = 1
        self.grid = g
        self.obst_version += 1

    def free(self, i, j):
        return 0 <= i < self.nx and 0 <= j < self.nz and not self.grid[j * self.nx + i]

    def cell(self, x, z):
        return min(self.nx - 1, max(0, int(x / CELL))), min(self.nz - 1, max(0, int(z / CELL)))

    def nearest_free(self, i, j):
        if self.free(i, j):
            return i, j
        seen, q = {(i, j)}, deque([(i, j)])
        while q:
            a, b = q.popleft()
            for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (a + da, b + db)
                if n in seen or not (0 <= n[0] < self.nx and 0 <= n[1] < self.nz):
                    continue
                if self.free(*n):
                    return n
                seen.add(n)
                if len(seen) > 4000:
                    return None
                q.append(n)
        return None

    def los(self, a, b):
        (x0, z0), (x1, z1) = a, b
        n = int(math.hypot(x1 - x0, z1 - z0) / (CELL * 0.5)) + 1
        for k in range(n + 1):
            t = k / n
            if not self.free(*self.cell(x0 + (x1 - x0) * t, z0 + (z1 - z0) * t)):
                return False
        return True

    def plan(self, start, goal):
        s = self.nearest_free(*self.cell(*start))
        g = self.nearest_free(*self.cell(*goal))
        if s is None or g is None:
            return None
        nx = self.nx
        h = lambda a: (abs(a[0] - g[0]) + abs(a[1] - g[1])) + (math.sqrt(2) - 2) * min(abs(a[0] - g[0]), abs(a[1] - g[1]))
        openh = [(h(s), 0.0, s)]
        gs, came = {s: 0.0}, {}
        while openh:
            _, gc, cur = heapq.heappop(openh)
            if cur == g:
                break
            if gc > gs.get(cur, 1e18):
                continue
            ci, cj = cur
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                ni, nj = ci + di, cj + dj
                if not self.free(ni, nj):
                    continue
                if di and dj and not (self.free(ci + di, cj) and self.free(ci, cj + dj)):
                    continue
                ng = gc + (1.4142 if di and dj else 1.0)
                if ng < gs.get((ni, nj), 1e18):
                    gs[(ni, nj)] = ng
                    came[(ni, nj)] = cur
                    heapq.heappush(openh, (ng + h((ni, nj)), ng, (ni, nj)))
        else:
            return None
        if g not in gs:
            return None
        cells = [g]
        while cells[-1] != s:
            cells.append(came[cells[-1]])
        cells.reverse()
        pts = [((i + 0.5) * CELL, (j + 0.5) * CELL) for i, j in cells]
        pts[0] = tuple(start) if self.free(*self.cell(*start)) else pts[0]
        if self.free(*self.cell(*goal)):
            pts[-1] = tuple(goal)
        # shortcut smoothing
        out, k = [pts[0]], 0
        while k < len(pts) - 1:
            m = len(pts) - 1
            while m > k + 1 and not self.los(pts[k], pts[m]):
                m -= 1
            out.append(pts[m])
            k = m
        if not self.free(*self.cell(*start)):
            out.insert(0, tuple(start))
        return out

    @staticmethod
    def path_len(p):
        return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(p, p[1:]))

    # ------------------------------------------------------------ targets
    def destinations(self):
        return list(ROOMS) + list(PLACES) + list(ITEMS)

    def resolve(self, target):
        """-> (label, x, z, heading or None) or None"""
        t = (target or "").strip().lower().replace(" ", "_").replace("-", "_")
        alias = {"me": "user", "you": "user", "sofa": "user", "couch": "user", "dock": "charging_station",
                 "charger": "charging_station", "home": "charging_station", "living": "living_room",
                 "lounge": "living_room", "door": "front_door", "entrance": "front_door", "milk": "stove",
                 "milk_pot": "stove", "oven": "stove", "television": "tv", "water": "water_bottle",
                 "remote": "tv_remote", "medicine_box": "medicine", "pills": "medicine", "sink": "kitchen_sink"}
        t = alias.get(t, t)
        if t in ROOMS:
            name, _, (x, z) = ROOMS[t]
            return name, x, z, None
        if t in PLACES:
            name, (x, z, h) = PLACES[t]
            return name, x, z, h
        if t in ITEMS:
            it = self.items[t]
            if it["carried"]:
                return None
            px, pz = (PEOPLE[it["holder"]][1][0], PEOPLE[it["holder"]][1][2]) if it["holder"] else (it["pos"][0], it["pos"][2])
            best = None
            for r in (0.75, 0.9, 1.05):
                for k in range(24):
                    a = k * math.pi / 12
                    cx, cz = px + r * math.cos(a), pz + r * math.sin(a)
                    i, j = self.cell(cx, cz)
                    if not self.free(i, j) or room_of(cx, cz) != room_of(px, pz):
                        continue
                    d = math.hypot(cx - self.x, cz - self.z)
                    if best is None or d < best[0]:
                        best = (d, cx, cz, math.atan2(pz - cz, px - cx))
            if best:
                return ITEMS[t][0], best[1], best[2], best[3]
        return None

    # ------------------------------------------------------------ simulation
    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        last = time.time()
        while True:
            time.sleep(1 / 30)
            now = time.time()
            dt = min(0.1, now - last) * self.time_scale
            last = now
            with self.lock:
                self.step(dt)

    def step(self, dt):
        # appliances (timing-insensitive to step size, run once on the full dt)
        if self.stove_on:
            self.milk_temp = min(100.0, self.milk_temp + 0.6 * dt)
            if self.milk_temp >= 99.5:
                self.boil_time += dt
                if self.boil_time > 60 and not self.boiled_over:
                    self.boiled_over = True
                    self.event("The milk is boiling over!", "warn")
        else:
            self.milk_temp = max(22.0, self.milk_temp - 0.4 * dt)
            self.boil_time = 0.0
        self.mast += max(-dt * 1.5, min(dt * 1.5, self.mast_target - self.mast))

        # Motion/collision is sensitive to step size (a coarse step can let the
        # robot clip a wall corner and freeze), so it always advances in small,
        # fixed-size substeps regardless of dt/time_scale.
        n = max(1, math.ceil(dt / 0.03))
        sub = dt / n
        for _ in range(n):
            self._kinematics_step(sub)

    def _kinematics_step(self, dt):
        v_cmd = w_cmd = 0.0
        nav = self.nav
        if nav and nav["status"] == "driving":
            if nav["ver"] != self.obst_version:
                p = self.plan((self.x, self.z), nav["goal"])
                nav["ver"] = self.obst_version
                if p is None:
                    nav["status"] = "failed"
                    nav["reason"] = "the way is blocked and there is no other route"
                    self.event("No route — the way is blocked.", "warn")
                else:
                    nav["path"], nav["wp"] = p, 1
                    nav["replans"] += 1
                    self.event("Obstacle on the route — re-planned a new path.", "warn")
            if nav["status"] == "driving":
                path = nav["path"]
                while True:
                    tx, tz = path[nav["wp"]]
                    d = math.hypot(tx - self.x, tz - self.z)
                    last_wp = nav["wp"] == len(path) - 1
                    if not last_wp and d < 0.12:
                        nav["wp"] += 1
                        continue
                    break
                if last_wp and d < 0.05:
                    nav["status"] = "turning"
                else:
                    err = wrap(math.atan2(tz - self.z, tx - self.x) - self.th)
                    w_cmd = max(-W_MAX, min(W_MAX, 3.0 * err))
                    if abs(err) < 0.6:
                        v_cmd = V_MAX * math.cos(err)
                        if last_wp:
                            v_cmd = min(v_cmd, 0.08 + 1.2 * d)
                remaining = d + self.path_len(path[nav["wp"]:])
                self.task = f"Driving to {nav['label']} ({remaining:.1f} m left)"
        if nav and nav["status"] == "turning":
            if nav["heading"] is None:
                nav["status"] = "arrived"
            else:
                err = wrap(nav["heading"] - self.th)
                w_cmd = max(-W_MAX, min(W_MAX, 3.5 * err))
                if abs(err) < 0.02:
                    nav["status"] = "arrived"
        if nav and nav["status"] in ("arrived", "failed"):
            self.nav = None if nav["status"] == "arrived" else nav
            self.nav = None
            self.last_nav = nav

        m = self.manual
        if m:
            if m["kind"] == "move":
                sp = min(V_MAX * 0.7, 0.05 + 1.5 * m["left"])
                v_cmd = sp * m["dir"]
            else:
                w_cmd = m["dir"] * min(W_MAX, 0.15 + 3 * m["left"])

        # sonar + safety stop (simulated ultrasonic sensor, like the real car)
        hits = [ray_rect(self.x, self.z, math.cos(self.th), math.sin(self.th), r) for r in self.obstacles()]
        hits = [h for h in hits if h is not None]
        self.sonar = max(0.0, min(hits) - 0.28) if hits else 4.0
        if v_cmd > 0 and self.sonar < 0.12:
            v_cmd = 0.0
            if m:
                m["blocked"] = True
            elif nav:
                self._build_grid()  # forces a re-plan

        # integrate with acceleration limits
        self.v += max(-1.5 * dt, min(1.5 * dt, v_cmd - self.v))
        self.w += max(-8 * dt, min(8 * dt, w_cmd - self.w))
        if v_cmd == 0 and abs(self.v) < 0.03:
            self.v = 0.0
        nx = self.x + self.v * math.cos(self.th) * dt
        nz = self.z + self.v * math.sin(self.th) * dt
        if all(rect_dist(nx, nz, r) > R_ROBOT - 0.04 for r in self.obstacles()):
            self.x, self.z = nx, nz
        else:
            self.v = 0.0
            if m:
                m["blocked"] = True
        self.th = wrap(self.th + self.w * dt)

        if m:
            if m["kind"] == "move":
                m["left"] -= abs(self.v) * dt
            else:
                m["left"] -= abs(self.w) * dt
            if m["left"] <= 0.005 or m.get("blocked"):
                self.manual = None
                self.last_manual = m
                self.v = self.w = 0.0

        self.battery -= (abs(self.v) * 0.4 + abs(self.w) * 0.05 + 0.003) * dt
        if self.docked and not self.nav and not self.manual:
            self.battery = min(100.0, self.battery + 1.5 * dt)
            if self.activity == "idle":
                self.task = "Docked, charging" if self.battery < 99.9 else "Docked, fully charged"
        self.battery = max(0.0, self.battery)

    # ------------------------------------------------------------ actions (blocking)
    def _wait(self, cond, epoch, timeout):
        end = time.time() + timeout / self.time_scale
        while time.time() < end:
            time.sleep(0.04)
            with self.lock:
                if self.epoch != epoch:
                    return "cancelled"
                if cond():
                    return "ok"
        return "timeout"

    def stop(self, why="Stopped by the user."):
        with self.lock:
            self.epoch += 1
            self.nav = self.manual = None
            self.v = self.w = 0.0
            self.activity = "idle"
            self.mast_target = 0.0
            self.task = "Stopped"
            self.event(why, "warn")

    def navigate(self, target):
        with self.lock:
            dest = self.resolve(target)
            if dest is None:
                return {"ok": False, "error": f"I don't know where '{target}' is."}
            label, gx, gz, gh = dest
            self.mast_target = 0.0
            path = self.plan((self.x, self.z), (gx, gz))
            if path is None:
                self.event(f"No route to {label}.", "warn")
                return {"ok": False, "error": f"No route to {label}: the way is blocked."}
            epoch = self.epoch
            self.nav = {"goal": (gx, gz), "heading": gh, "path": path, "wp": 1 if len(path) > 1 else 0,
                        "label": label, "status": "driving", "ver": self.obst_version, "replans": 0}
            self.activity = "driving"
            dist = self.path_len(path)
            self.event(f"Planned a {dist:.1f} m route to {label}.")
        res = self._wait(lambda: self.nav is None, epoch, 180)
        with self.lock:
            self.activity = "idle"
            nav = getattr(self, "last_nav", None)
            if res != "ok":
                self.nav = None
                self.v = self.w = 0.0
                return {"ok": False, "error": "Navigation was " + res}
            if nav["status"] == "failed":
                return {"ok": False, "error": f"Could not reach {label}: {nav['reason']}"}
            self.task = f"At the {label}" if not label.startswith(("you", "Grandpa")) else f"With {label.split(',')[0]}"
            self.event(f"Arrived at {label}.", "ok")
            return {"ok": True, "arrived": label, "room": ROOMS[room_of(self.x, self.z)][0],
                    "route_m": round(dist, 1), "replanned": nav["replans"], "battery": round(self.battery)}

    def _milk_level(self):
        if self.boiled_over:
            return "boiling_over", "the milk is BOILING OVER - foam is spilling onto the stove"
        if self.milk_temp >= 99.5:
            return "boiling", "the milk is boiling - big bubbles and lots of steam"
        if self.milk_temp >= 85:
            return "very_hot", "the milk is very hot and steaming, small bubbles at the edge, not boiling yet"
        if self.milk_temp >= 45:
            return "warm", "the milk is warm, faint vapour, no bubbles"
        return "cold", "the milk is cold, no steam"

    def _describe(self, oid):
        if oid == "milk_pot":
            return "Milk pot on the stove: " + self._milk_level()[1] + "."
        if oid == "stove":
            return "Stove: burner is ON (glowing red)." if self.stove_on else "Stove: burner is OFF."
        if oid == "tv":
            return "TV: on, showing the news." if self.tv_on else "TV: off."
        if oid == "front_door":
            return "Front door: OPEN." if self.door_open else "Front door: closed."
        if oid in PEOPLE:
            held = [ITEMS[k][0] for k, it in self.items.items() if it["holder"] == oid]
            who = "You (the user) sitting on the sofa" if oid == "user" else "Grandpa sitting in his armchair"
            return who + (", holding the " + ", ".join(held) if held else "") + "."
        if oid in ITEMS:
            it = self.items[oid]
            where = f"on the {FURNITURE[it['on']][4]}" if it["on"] else "on the floor"
            return f"{ITEMS[oid][0].capitalize()} {where}."
        return oid

    def _obj_pos(self, oid):
        if oid in APPLIANCES:
            p = APPLIANCES[oid][1]
        elif oid in PEOPLE:
            p = PEOPLE[oid][1]
        else:
            it = self.items[oid]
            if it["carried"]:
                return None
            p = it["pos"]
        return p[0], p[2]

    def perceivable(self):
        return list(APPLIANCES) + list(PEOPLE) + list(ITEMS)

    def _visible(self, oid, fov=True):
        p = self._obj_pos(oid)
        if p is None:
            return None
        dx, dz = p[0] - self.x, p[1] - self.z
        d = math.hypot(dx, dz)
        if d > 6.0 or d < 0.05:
            return None
        bearing = wrap(math.atan2(dz, dx) - self.th)
        if fov and abs(bearing) > math.radians(34):
            return None
        for r in self.obstacles(tall_only=True):
            if r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]:
                continue
            t = ray_rect(self.x, self.z, dx / d, dz / d, r)
            if t is not None and t < d - 0.05:
                return None
        return d, bearing

    def look(self, target=None):
        with self.lock:
            epoch = self.epoch
            self.mast_target = 1.0
            self.activity = "looking"
            face = None
            if target:
                t = {"milk": "milk_pot", "pot": "milk_pot", "me": "user", "door": "front_door", "remote": "tv_remote",
                     "water": "water_bottle", "television": "tv"}.get(target, target)
                if t not in self.perceivable():
                    return {"ok": False, "error": f"Unknown thing '{target}'."}
                target = t
                vis = self._visible(target, fov=False)
                if vis is None:
                    p = self._obj_pos(target)
                    room = ROOMS[room_of(*p)][0] if p else "?"
                    self.activity = "idle"
                    return {"ok": True, "visible": False,
                            "result": f"I can't see the {target.replace('_', ' ')} from here (it is in the {room}). Navigate closer first."}
                p = self._obj_pos(target)
                face = math.atan2(p[1] - self.z, p[0] - self.x)
                self.task = f"Looking at the {target.replace('_', ' ')}"
            else:
                self.task = "Looking around"
        if face is not None:
            self.manual = None
            with self.lock:
                self.nav = {"goal": (self.x, self.z), "heading": face, "path": [(self.x, self.z)], "wp": 0,
                            "label": "target", "status": "turning", "ver": self.obst_version, "replans": 0}
            self._wait(lambda: self.nav is None, epoch, 10)
        if self._wait(lambda: self.mast > 0.97, epoch, 5) == "cancelled":
            return {"ok": False, "error": "cancelled"}
        time.sleep(0.6 / self.time_scale)
        with self.lock:
            seen = []
            for oid in self.perceivable():
                vis = self._visible(oid)
                if vis is None:
                    continue
                d, b = vis
                small = oid in ITEMS or oid == "milk_pot"
                if small and d > 3.5:
                    desc = f"{oid.replace('_', ' ')} (too far to see details)"
                else:
                    desc = self._describe(oid)
                side = "ahead" if abs(b) < 0.2 else ("to the right" if b > 0 else "to the left")
                seen.append({"id": oid, "what": desc, "distance_m": round(d, 1), "where": side})
            seen.sort(key=lambda s: s["distance_m"])
            self.detections = [{"id": s["id"], "label": s["what"].split(":")[0].split(".")[0][:40], "t": time.time()}
                               for s in seen[:6]]
            self.activity = "idle"
            room = ROOMS[room_of(self.x, self.z)][0]
            self.event(f"Camera check in the {room}: {len(seen)} thing(s) in view.")
            focus = next((s["what"] for s in seen if s["id"] == target), None)
            return {"ok": True, "room": room, "target": focus, "in_view": seen[:8]}

    def watch(self, target, max_seconds=60):
        first = self.look(target)
        if not first.get("ok") or first.get("visible") is False or target not in ("milk_pot", "milk", "pot"):
            return first
        with self.lock:
            start_level = self._milk_level()[0]
            epoch = self.epoch
            self.task = "Watching the milk"
            self.activity = "looking"
        res = self._wait(lambda: self._milk_level()[0] != start_level, epoch, min(120, max_seconds))
        with self.lock:
            self.activity = "idle"
            return {"ok": True, "changed": res == "ok", "now": self._describe("milk_pot"), "result": res}

    def pick_up(self, item):
        with self.lock:
            item = {"water": "water_bottle", "remote": "tv_remote", "pills": "medicine"}.get(item, item)
            if item not in ITEMS:
                return {"ok": False, "error": f"Unknown item '{item}'."}
            it = self.items[item]
            if it["carried"]:
                return {"ok": False, "error": f"I'm already carrying the {ITEMS[item][0]}."}
            p = self._obj_pos(item)
            if math.hypot(p[0] - self.x, p[1] - self.z) > REACH:
                return {"ok": False, "error": f"The {ITEMS[item][0]} is out of reach. navigate_to('{item}') first."}
            if sum(1 for i in self.items.values() if i["carried"]) >= 2:
                return {"ok": False, "error": "My tray is full (2 items)."}
            epoch = self.epoch
            self.activity = "working"
            self.task = f"Picking up the {ITEMS[item][0]}"
        if self._wait(lambda: False, epoch, 1.2) == "cancelled":
            return {"ok": False, "error": "cancelled"}
        with self.lock:
            it.update(carried=True, holder=None, on=None)
            self.activity = "idle"
            self.event(f"Picked up the {ITEMS[item][0]}.", "ok")
            return {"ok": True, "carrying": [ITEMS[k][0] for k, i in self.items.items() if i["carried"]]}

    def drop_off(self, item=None):
        with self.lock:
            carried = [k for k, i in self.items.items() if i["carried"]]
            if item:
                item = {"water": "water_bottle", "remote": "tv_remote"}.get(item, item)
                carried = [k for k in carried if k == item]
            if not carried:
                return {"ok": False, "error": "I'm not carrying that."}
            epoch = self.epoch
            self.activity = "working"
        if self._wait(lambda: False, epoch, 1.0) == "cancelled":
            return {"ok": False, "error": "cancelled"}
        with self.lock:
            self.activity = "idle"
            person = min(PEOPLE, key=lambda p: math.hypot(PEOPLE[p][1][0] - self.x, PEOPLE[p][1][2] - self.z))
            pp = PEOPLE[person][1]
            out = []
            for n, k in enumerate(carried):
                it = self.items[k]
                if math.hypot(pp[0] - self.x, pp[2] - self.z) <= REACH + 0.2:
                    it.update(carried=False, holder=person, on=None,
                              pos=[pp[0] + 0.25 * math.cos(self.th + math.pi), 0.75 + 0.1 * n, pp[2] + 0.25 * math.sin(self.th + math.pi)])
                    out.append(f"Handed the {ITEMS[k][0]} to {PEOPLE[person][0]}")
                else:
                    best = None
                    for fid, (typ, r, h, _, name) in FURNITURE.items():
                        if typ in ("rug", "dock") or h > 1.3 or h < 0.3:
                            continue
                        d = rect_dist(self.x, self.z, r)
                        if d < 0.9 and (best is None or d < best[0]):
                            best = (d, fid, r, h)
                    if best:
                        _, fid, r, h = best
                        px = min(max(self.x, r[0] + 0.1), r[2] - 0.1) + 0.12 * n
                        pz = min(max(self.z, r[1] + 0.1), r[3] - 0.1)
                        it.update(carried=False, holder=None, on=fid, pos=[px, h, pz])
                        out.append(f"Put the {ITEMS[k][0]} on the {FURNITURE[fid][4]}")
                    else:
                        it.update(carried=False, holder=None, on=None,
                                  pos=[self.x + 0.5 * math.cos(self.th), 0.0, self.z + 0.5 * math.sin(self.th)])
                        out.append(f"Put the {ITEMS[k][0]} on the floor")
            for o in out:
                self.event(o + ".", "ok")
            self.task = out[-1]
            return {"ok": True, "result": "; ".join(out)}

    def operate(self, appliance, action):
        with self.lock:
            appliance = {"milk": "stove", "milk_pot": "stove", "door": "front_door", "television": "tv"}.get(appliance, appliance)
            if appliance not in ("stove", "tv", "front_door"):
                return {"ok": False, "error": f"I can't operate '{appliance}'."}
            p = APPLIANCES[appliance][1]
            if math.hypot(p[0] - self.x, p[2] - self.z) > 1.6:
                return {"ok": False, "error": f"Too far from the {appliance.replace('_', ' ')}. navigate_to('{appliance}') first."}
            epoch = self.epoch
            self.activity = "working"
            self.task = f"Operating the {appliance.replace('_', ' ')}"
        if self._wait(lambda: False, epoch, 1.5) == "cancelled":
            return {"ok": False, "error": "cancelled"}
        with self.lock:
            on = action in ("on", "open")
            if appliance == "stove":
                self.stove_on = on
            elif appliance == "tv":
                self.tv_on = on
            else:
                self.door_open = on
                self._build_grid()
            self.activity = "idle"
            msg = f"{APPLIANCES[appliance][0].capitalize()} is now {'on' if on and appliance != 'front_door' else 'open' if on else 'closed' if appliance == 'front_door' else 'off'}."
            self.event(msg, "ok")
            return {"ok": True, "result": msg}

    def go_charge(self):
        r = self.navigate("charging_station")
        if not r.get("ok"):
            return r
        with self.lock:
            self.task = "Docked, charging"
            self.event("Docked. Charging.", "ok")
            return {"ok": True, "docked": True, "battery": round(self.battery)}

    def move(self, direction, distance_m):
        d = max(0.05, min(abs(float(distance_m)), 3.0))
        with self.lock:
            epoch = self.epoch
            self.nav = None
            self.manual = {"kind": "move", "dir": 1 if direction == "forward" else -1, "left": d}
            self.task = f"Moving {direction} {d:.1f} m"
        res = self._wait(lambda: self.manual is None, epoch, 30)
        with self.lock:
            m = getattr(self, "last_manual", {})
            if m.get("blocked"):
                self.event("Obstacle ahead — stopped.", "warn")
                return {"ok": False, "error": "Blocked by an obstacle", "moved_m": round(d - m["left"], 2)}
            return {"ok": res == "ok", "moved_m": round(d, 2)}

    def turn(self, direction, degrees):
        a = math.radians(max(1, min(abs(float(degrees)), 360)))
        with self.lock:
            epoch = self.epoch
            self.nav = None
            self.manual = {"kind": "turn", "dir": 1 if direction == "right" else -1, "left": a}
            self.task = f"Turning {direction}"
        res = self._wait(lambda: self.manual is None, epoch, 30)
        return {"ok": res == "ok", "turned_deg": round(math.degrees(a))}

    def status(self):
        with self.lock:
            return {"room": ROOMS[room_of(self.x, self.z)][0], "battery": round(self.battery),
                    "docked": self.docked, "doing": self.task,
                    "carrying": [ITEMS[k][0] for k, i in self.items.items() if i["carried"]]}

    # ------------------------------------------------------------ scenario controls
    def control(self, action, x=None, z=None):
        with self.lock:
            if action == "stove_on":
                self.stove_on = True
            elif action == "stove_off":
                self.stove_on = False
            elif action == "milk_cold":
                self.milk_temp, self.boil_time, self.boiled_over = 22.0, 0.0, False
            elif action == "milk_almost":
                self.milk_temp, self.boil_time, self.boiled_over, self.stove_on = 92.0, 0.0, False, True
            elif action == "milk_boil":
                self.milk_temp, self.boil_time, self.boiled_over, self.stove_on = 100.0, 0.0, False, True
            elif action in ("tv_on", "tv_off"):
                self.tv_on = action == "tv_on"
            elif action in ("door_open", "door_close"):
                self.door_open = action == "door_open"
                self._build_grid()
            elif action == "block_hallway":
                for bx, bz in BOX_SPOTS:
                    self.boxes.append((bx - 0.27, bz - 0.27, bx + 0.27, bz + 0.27))
                self._build_grid()
                self.event("Boxes dropped in the hallway.", "warn")
            elif action == "add_box" and x is not None:
                if math.hypot(x - self.x, z - self.z) < 0.7:
                    return {"ok": False, "error": "Too close to the robot"}
                self.boxes.append((x - 0.27, z - 0.27, x + 0.27, z + 0.27))
                self._build_grid()
                self.event("A box was placed.", "warn")
            elif action == "clear_boxes":
                self.boxes = []
                self._build_grid()
            elif action == "battery_low":
                self.battery = 14.0
            elif action == "reset":
                pass
            else:
                return {"ok": False, "error": "unknown action"}
        if action == "reset":
            self.reset()
        return {"ok": True}

    # ------------------------------------------------------------ snapshots
    def snapshot(self):
        with self.lock:
            nav = self.nav
            return {
                "robot": {"x": self.x, "z": self.z, "th": self.th, "v": self.v, "w": self.w, "mast": self.mast,
                          "battery": self.battery, "docked": self.docked, "activity": self.activity,
                          "room": ROOMS[room_of(self.x, self.z)][0], "task": self.task, "sonar": self.sonar},
                "path": [list(p) for p in nav["path"][nav["wp"] - 1 if nav["wp"] else 0:]] if nav else [],
                "goal": list(nav["goal"]) if nav else None,
                "stove_on": self.stove_on, "milk_temp": self.milk_temp, "milk_level": self._milk_level()[0],
                "tv_on": self.tv_on, "door_open": self.door_open,
                "items": {k: {"pos": i["pos"], "carried": i["carried"],
                              "slot": [k2 for k2, i2 in self.items.items() if i2["carried"]].index(k) if i["carried"] else -1}
                          for k, i in self.items.items()},
                "boxes": self.boxes, "events": list(self.events)[-12:], "speech": self.speech, "heard": self.heard,
                "detections": [d for d in self.detections if time.time() - d["t"] < 8], "busy": self.busy,
            }

    def static_map(self):
        return {"size": [W, H], "walls": WALLS, "wall_h": 2.5, "front_door": FRONT_DOOR_RECT,
                "rooms": {k: {"name": n, "rect": r, "spot": s} for k, (n, r, s) in ROOMS.items()},
                "furniture": {k: {"type": t, "rect": r, "h": h, "facing": f, "name": n} for k, (t, r, h, f, n) in FURNITURE.items()},
                "places": {k: {"name": n, "pose": p} for k, (n, p) in PLACES.items()},
                "people": {k: {"name": n, "pos": p} for k, (n, p) in PEOPLE.items()},
                "items": {k: {"name": n} for k, (n, p) in ITEMS.items()},
                "appliances": {k: {"name": n, "pos": p} for k, (n, p) in APPLIANCES.items()}}
