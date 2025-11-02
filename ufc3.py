# ultimate_field_optimized.py
# Compact Ultimate field renderer with drag, hover, CSV import/export, play recording + slider playback
# Run: python ultimate_field_optimized.py

import pygame
import math
import os
import csv
import time
import sys
from ufc_logger import UFCLogger

# ============ Configuration ============
CONFIG_DIR = os.path.expanduser("~/Documents/ultimate_configs")
os.makedirs(CONFIG_DIR, exist_ok=True)

# Field dimensions (meters)
FIELD_LEN, FIELD_WID, ENDZONE, BRICK_OFF = 100.0, 37.0, 18.0, 18.0
GOAL_L, GOAL_R = ENDZONE, FIELD_LEN - ENDZONE
BRICK_L, BRICK_R = GOAL_L + BRICK_OFF, GOAL_R - BRICK_OFF
CENTER_Y = FIELD_WID / 2

# Display
WIN_W, WIN_H = 1200, 780
MARGIN_L, MARGIN_T = 60, 40
UI_BAR_H, RECORD_BAR_H = 56, 72
DISC_R = 0.6

# Colors
COL = {
    'bg': (18,18,20), 'field': (18,110,45), 'ez': (12,85,35), 'line': (250,250,250),
    'brick': (255,215,0), 'blue': (40,120,255), 'red': (255,70,70), 'disc': (50,50,50),
    'grid_minor': (34,140,70), 'grid_major': (60,170,95), 'tick': (220,235,220),
    'sel': (255,255,255), 'accent': (90,170,240)
}

# Snapping (meters)
SNAP = {'hard': 0.20, 'soft': 0.60, 'pull': 0.60}

CSV_HEADERS = ["entity", "label", "team", "x_m", "y_m"]

# ============ Utilities ============
def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# give a tiny extra height budget so recording bar can overlap slightly and reduce empty band
def compute_scale(w, h):
    return min((w - 2*MARGIN_L) / FIELD_LEN,
               (h - 2*MARGIN_T - UI_BAR_H - RECORD_BAR_H + 8) / FIELD_WID)

def handle_save_log(logger, toasts):
    try:
        filepath = logger.save_log()
        toasts.show(f"Log saved to {os.path.basename(filepath)}")
        logger.log_system_event("log_saved", {"filepath": filepath})
    except Exception as e:
        toasts.show("Error saving log")
        logger.log_error("save_log_error", str(e), "")

def dist_point_seg(px, py, x1, y1, x2, y2):
    vx, vy = x2-x1, y2-y1
    wx, wy = px-x1, py-y1
    L2 = vx*vx + vy*vy
    if not L2:
        return math.hypot(px-x1, py-y1)

    t = clamp((wx*vx+wy*vy) / L2, 0, 1)
    return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))

def ensure_csv_ext(name):
    if not name.lower().endswith('.csv'):
        return name + '.csv'
    return name

# ============ UI Components ============
class Button:
    def __init__(self, rect, text):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.hover = self.enabled = self.visible = True
        # visual tweaks
        self.icon = None
        self.primary = False
        self.corner_radius = 10
    
    def draw(self, surf, font):
        if not self.visible:
            return
        # primary buttons brighter accent
        if self.primary and self.enabled:
            base_col = (90,170,240)
        else:
            base_col = (100, 160, 210) if self.enabled else (90,90,90)
        # hover brighten
        if self.hover and self.enabled:
            col = tuple(min(255, int(c*1.08)) for c in base_col)
        else:
            col = base_col
        pygame.draw.rect(surf, col, self.rect, border_radius=self.corner_radius)
        pygame.draw.rect(surf, (0,0,0), self.rect, 2, border_radius=self.corner_radius)
        # icon + text
        txt = f"{(self.icon + ' ') if self.icon else ''}{self.text}"
        lbl = font.render(txt, True, (255,255,255))
        surf.blit(lbl, (self.rect.centerx-lbl.get_width()//2, self.rect.centery-lbl.get_height()//2))
    
    def update(self, pos):
        if self.visible:
            self.hover = self.enabled and self.rect.collidepoint(*pos)
    
    def clicked(self, pos):
        return self.visible and self.enabled and self.rect.collidepoint(*pos)

class Toasts:
    def __init__(self):
        self.q = []
    def show(self, text, sec=2.2, kind=None):
        # kind: 'success', 'warn', 'info'
        self.q.append((text, time.time()+sec, kind))
    
    def draw(self, screen, font):
        # keep only active toasts
        now = time.time()
        self.q = [(t,e,k) for t,e,k in self.q if e>now]
        if not self.q:
            return
        text, _, kind = self.q[-1]
        lbl = font.render(text, True, (255,255,255))
        w, h = lbl.get_width()+24, lbl.get_height()+14
        x, y = WIN_W//2-w//2, MARGIN_T-h-8 if MARGIN_T>24 else 8
        bg = pygame.Surface((w,h+8), pygame.SRCALPHA)
        # color by kind
        if kind == 'success':
            base_col = (30,160,70,220)
        elif kind == 'warn':
            base_col = (200,140,20,220)
        else:
            base_col = (20,20,24,220)
        bg.fill((0,0,0,0))
        pygame.draw.rect(bg, base_col, pygame.Rect(0,0,w,h), border_radius=10)
        pygame.draw.polygon(bg, base_col, [(w//2-8,h),(w//2+8,h),(w//2,h+8)])
        pygame.draw.rect(bg, (255,255,255,30), pygame.Rect(0,0,w,h), 1, border_radius=10)
        screen.blit(bg, (x,y))
        screen.blit(lbl, (x+12,y+6))

def make_button(rect, text, icon=None, primary=False):
    b = Button(rect, text)
    b.icon = icon
    b.primary = primary
    b.corner_radius = 10
    return b

class ExportDialog:
    def __init__(self, font, small):
        self.font, self.small = font, small
        self.visible = False
        self.text = ""
        self.mode = "position"
        w, h = 640, 200
        self.box = pygame.Rect(WIN_W//2-w//2, WIN_H//2-h//2, w, h)
        self.input = pygame.Rect(self.box.left+20, self.box.top+70, w-40, 36)
        self.ok = Button((self.box.right-210, self.box.bottom-50, 90, 34), "OK")
        self.cancel = Button((self.box.right-110, self.box.bottom-50, 90, 34), "Cancel")
        self.cursor_on = True
        self.last = time.time()
        self.focus = True
    
    def open(self):
        prefix = "ultimate" if self.mode == "position" else "strategy"
        self.text = f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        self.visible = self.focus = True
    
    def close(self):
        self.visible = False
    
    def draw(self, screen):
        if not self.visible:
            return None
        ov = pygame.Surface((WIN_W,WIN_H), pygame.SRCALPHA)
        ov.fill((0,0,0,160))
        screen.blit(ov, (0,0))
        pygame.draw.rect(screen, (34,34,40), self.box, border_radius=12)
        pygame.draw.rect(screen, (0,0,0), self.box, 2, border_radius=12)
        screen.blit(self.font.render("Export configuration", True, (235,235,235)), (self.box.left+20, self.box.top+20))
        screen.blit(self.small.render(f"Saving to: {CONFIG_DIR}", True, (210,210,210)), (self.box.left+20, self.box.top+44))
        pygame.draw.rect(screen, (54,54,60), self.input, border_radius=6)
        pygame.draw.rect(screen, (0,0,0), self.input, 2, border_radius=6)
        txt = self.font.render(self.text, True, (240,240,240))
        screen.blit(txt, (self.input.left+10, self.input.top+6))
        if time.time()-self.last > 0.5:
            self.cursor_on = not self.cursor_on
            self.last = time.time()
        if self.focus and self.cursor_on:
            cx = self.input.left+10+txt.get_width()+2
            pygame.draw.line(screen, (255,255,255), (cx,self.input.top+6), (cx,self.input.bottom-6), 2)
        self.ok.draw(screen, self.font)
        self.cancel.draw(screen, self.font)
    
    def handle(self, e):
        if not self.visible:
            return None
        if e.type == pygame.MOUSEMOTION:
            self.ok.update(e.pos)
            self.cancel.update(e.pos)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.ok.clicked(e.pos):
                return self.confirm()
            if self.cancel.clicked(e.pos):
                self.close()
                return None
            self.focus = self.input.collidepoint(*e.pos)
        elif e.type == pygame.KEYDOWN and self.focus:
            if e.key == pygame.K_RETURN:
                return self.confirm()
            if e.key == pygame.K_ESCAPE:
                self.close()
                return None
            if e.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif e.unicode and (e.unicode.isalnum() or e.unicode in "_-. "):
                self.text += e.unicode
        return None
    
    def confirm(self):
        name = self.text.strip() or f"ultimate_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        name = ensure_csv_ext(name)
        self.close()
        return name

class Picker:
    def __init__(self, font):
        self.font = font
        self.visible = False
        self.sort = "date_desc"
        self.scroll = 0
        self.mode = "position"
        self._cache = {}
        w, h = 640, 420
        self.box = pygame.Rect(WIN_W//2-w//2, WIN_H//2-h//2, w, h)
    
    def files(self):
        now = time.time()
        if not self._cache or now-self._cache.get('t',0) > 1.5:
            lst = [f for f in os.listdir(CONFIG_DIR) if f.lower().endswith(".csv")]
            info = [(f, os.path.getmtime(os.path.join(CONFIG_DIR,f))) for f in lst]
            self._cache = {'t': now, 'v': info}
        info = self._cache['v']
        def _picker_key(x):
            if self.sort.startswith("name"):
                return x[0].lower()
            return x[1]

        return sorted(info, key=_picker_key, reverse=self.sort.endswith("desc"))
    
    def handle(self, e):
        if not self.visible:
            return None
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.visible = False
            elif e.key == pygame.K_n:
                if self.sort != "name_asc":
                    self.sort = "name_asc"
                else:
                    self.sort = "name_desc"
            elif e.key == pygame.K_d:
                if self.sort != "date_desc":
                    self.sort = "date_desc"
                else:
                    self.sort = "date_asc"
            elif e.key == pygame.K_UP:
                self.scroll = max(0, self.scroll-1)
            elif e.key == pygame.K_DOWN:
                self.scroll += 1
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 4:
                self.scroll = max(0, self.scroll-1)
            elif e.button == 5:
                self.scroll += 1
            elif e.button == 1:
                # Click inside picker - resolve which file was clicked
                mx, my = e.pos
                if self.box.collidepoint(mx, my):
                    items = self.files()
                    top, rowh = self.box.top+64, 26
                    idx = (my - top)//rowh + self.scroll
                    if 0 <= idx < len(items):
                        return items[idx][0]
        return None
    
    def draw(self, screen):
        if not self.visible:
            return None
        ov = pygame.Surface((WIN_W,WIN_H), pygame.SRCALPHA)
        ov.fill((0,0,0,160))
        screen.blit(ov, (0,0))
        pygame.draw.rect(screen, (32,32,36), self.box, border_radius=12)
        pygame.draw.rect(screen, (0,0,0), self.box, 2, border_radius=12)
        screen.blit(self.font.render(f"Import from: {CONFIG_DIR}", True, (230,230,230)), (self.box.left+16, self.box.top+16))
        screen.blit(self.font.render(f"Sort: {self.sort}  (N/D, ↑/↓)", True, (200,200,200)), (self.box.left+16, self.box.top+36))

        mx, my = pygame.mouse.get_pos()
        items = self.files()
        top, rowh = self.box.top+64, 26

        for i, (fn,mt) in enumerate(items[self.scroll:self.scroll+14]):
            y = top + i*rowh
            r = pygame.Rect(self.box.left+16, y, self.box.width-32, rowh-4)
            hov = r.collidepoint(mx,my)
            pygame.draw.rect(screen, (60,60,66) if hov else (44,44,50), r, border_radius=6)
            stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(mt))
            screen.blit(self.font.render(f"{fn}   —   {stamp}", True, (240,240,240)), (r.left+8, r.top+4))
            # draw only; click handled in handle()

        screen.blit(self.font.render("Click a file to import • ESC to cancel", True, (220,220,220)), (self.box.left+16, self.box.bottom-34))
        return None

class Slider:
    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.min_v = self.max_v = self.value = 0.0
        self.dragging = False
        self.visible = self.enabled = False
    
    def set_range(self, lo, hi):
        self.min_v, self.max_v = float(lo), float(hi)
        self.value = clamp(self.value, self.min_v, self.max_v)
    
    def set_value(self, v):
        self.value = clamp(float(v), self.min_v, self.max_v)
    
    def _value_to_x(self, v):
        if self.max_v == self.min_v:
            return self.rect.left
        t = (v-self.min_v) / (self.max_v-self.min_v)
        return int(self.rect.left + t*self.rect.width)
    
    def _x_to_value(self, x):
        if self.max_v == self.min_v:
            return self.min_v
        t = (x-self.rect.left) / max(1, self.rect.width)
        return clamp(self.min_v + t*(self.max_v-self.min_v), self.min_v, self.max_v)
    
    def handle(self, e):
        if not (self.visible and self.enabled):
            return None
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.rect.collidepoint(*e.pos):
                self.dragging = True
                self.set_value(self._x_to_value(e.pos[0]))
                return self.value
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.dragging = False
        elif e.type == pygame.MOUSEMOTION and self.dragging:
            self.set_value(self._x_to_value(e.pos[0]))
            return self.value
        return None
    
    def draw(self, surf, font):
        if not self.visible:
            return
        # base track
        pygame.draw.rect(surf, (60,60,66), self.rect, border_radius=6)
        pygame.draw.rect(surf, (0,0,0), self.rect, 2, border_radius=6)
        # filled played portion
        kx = self._value_to_x(self.value)
        if kx > self.rect.left:
            played = pygame.Rect(self.rect.left+2, self.rect.top+4, kx - self.rect.left-4, self.rect.height-8)
            pygame.draw.rect(surf, (*COL['accent'],), played, border_radius=6)
        # Ticks: decimate when long
        span = max(1, int(math.ceil(self.max_v - self.min_v)))
        max_ticks = 80
        step = 1 if span <= max_ticks else int(math.ceil(span / max_ticks))
        for v in range(int(self.min_v), int(self.max_v)+1, step):
            x = self._value_to_x(v)
            pygame.draw.line(surf, (200,200,200,100), (x, self.rect.top+4), (x, self.rect.top+10))
        # Knob (bigger)
        knob_r = 13
        pygame.draw.circle(surf, COL['sel'] if self.dragging else COL['accent'], (kx, self.rect.centery), knob_r)
        pygame.draw.circle(surf, (0,0,0), (kx, self.rect.centery), knob_r, 2)
        # Label/timecode
        lbl = font.render(f"Step: {int(self.value) if abs(self.value-round(self.value))<1e-6 else f'{self.value:.2f}'}", True, (235,235,235))
        surf.blit(lbl, (self.rect.right+12, self.rect.centery-lbl.get_height()//2))

# ============ Recording ============
class RecordingManager:
    def __init__(self):
        self.state = None
        self.data = {}
        self.step = self.max_step = 0.0
        # cache full snapshots to avoid rebuilding from deltas for every scrub
        # key: integer step -> {'players': {label: [x,y], ...}, 'disc': [x,y] or None}
        self._snapshot_cache = {}

        # ---------- NEW: temporary link data + move bookkeeping ----------
        # temp stores UI-ish/transient info; never exported to CSV directly
        # links: {leader_label: {follower_label: delay_steps, ...}, ...}
        # followers index is derived on demand
        self.temp = {'links': {}}
        # when did a leader start moving? {label: step_int}
        self._move_started_at = {}
        # cache: reverse map for quick follower lookup {leader: [(follower, delay), ...]}
        self._followers_cache = None
        # -----------------------------------------------------------------

    def _rebuild_followers_cache(self):
        """Build reverse map: leader -> list[(follower, delay)]."""
        fol = {}
        for lead, fmap in self.temp.get('links', {}).items():
            for f, d in fmap.items():
                fol.setdefault(lead, []).append((f, int(d)))
        self._followers_cache = fol

    # ---------- NEW: public helpers to manage links (used by Scene) ----------
    def link_players(self, leader_label, follower_label, delay_steps=1):
        """Create/overwrite a link: follower follows leader after delay_steps."""
        if leader_label == follower_label:
            return  # ignore self-link
        self.temp.setdefault('links', {}).setdefault(leader_label, {})[follower_label] = int(max(0, delay_steps))
        self._followers_cache = None  # invalidate

    def unlink_player(self, follower_label=None, leader_label=None):
        """Remove links by follower or leader. If both None -> no-op."""
        if leader_label is not None:
            if leader_label in self.temp.get('links', {}):
                del self.temp['links'][leader_label]
        if follower_label is not None:
            # remove follower from all leaders
            for lead in list(self.temp.get('links', {}).keys()):
                if follower_label in self.temp['links'][lead]:
                    del self.temp['links'][lead][follower_label]
                    if not self.temp['links'][lead]:
                        del self.temp['links'][lead]
        self._followers_cache = None
    # ------------------------------------------------------------------------

    def reset(self):
        self.__init__()
        self._snapshot_cache.clear()

    def start_recording(self):
        self.state = 'recording'
        self.data.clear()
        self.step = self.max_step = 0.0
        self._snapshot_cache.clear()
        self._move_started_at.clear()

    def _prev_full_snapshot(self, t_minus_1):
        """Utility: full snapshot at t-1 if it exists, else None."""
        if t_minus_1 < 0 or not self.data:
            return None
        if t_minus_1 == 0 and 0 in self.data:
            return self.build_snapshot(0)
        if t_minus_1 in self.data or t_minus_1 <= max(self.data.keys()):
            # build from cache + deltas
            return self.build_snapshot(t_minus_1)
        return None

    def save_step(self, scene):
        """Save only changed players/disc for this step (sparse).

        NEW: during recording, followers auto-update based on links and delay.
        """
        t = int(round(self.step))

        # Build previous FULL snapshot (not just sparse entry)
        prev_full = self._prev_full_snapshot(t-1)

        # Always save full snapshot at step 0
        if t == 0 or prev_full is None:
            players_snap = {p['label']: [float(p['pos_m'][0]), float(p['pos_m'][1])] for p in scene.players}
            self.data[t] = {'players': players_snap, 'disc': [float(scene.disc['pos_m'][0]), float(scene.disc['pos_m'][1])]}
            self._snapshot_cache = {k: v for k, v in self._snapshot_cache.items() if k < t}
            # initialize move-start map
            for lab, pos in players_snap.items():
                self._move_started_at[lab] = t  # baseline
            return

        # ---------- Detect changes vs full previous snapshot ----------
        changed = {}
        curr_map = {p['label']: [float(p['pos_m'][0]), float(p['pos_m'][1])] for p in scene.players}
        prev_map = prev_full.get('players', {}) if prev_full else {}

        leaders_changed = []
        for lab, pos in curr_map.items():
            pp = prev_map.get(lab)
            if (pp is None) or (round(pp[0], 6) != round(pos[0], 6) or round(pp[1], 6) != round(pos[1], 6)):
                changed[lab] = pos
                leaders_changed.append(lab)

        # ---------- NEW: follower auto-move (only in recording state) ----------
        if self.state == 'recording' and changed:
            if self._followers_cache is None:
                self._rebuild_followers_cache()

            # mark/refresh move start times for leaders that changed at this step
            for lead in leaders_changed:
                self._move_started_at[lead] = t

            # For each changed leader, evaluate followers
            for lead in leaders_changed:
                followers = self._followers_cache.get(lead, [])
                if not followers:
                    continue
                leader_new = curr_map.get(lead)
                start_t = self._move_started_at.get(lead, t)

                for fol_lab, delay in followers:
                    # If enough steps have passed since leader started, teleport follower to leader's new position
                    if (t - start_t) >= delay:
                        # Update the Scene immediately so the UI shows the jump right after "Next Step"
                        if fol_lab in curr_map:
                            fx, fy = leader_new[0], leader_new[1]
                            # mutate scene (meters + pixels)
                            idx = scene._player_index_map.get(fol_lab)
                            if idx is not None:
                                scene.players[idx]['pos_m'] = [fx, fy]
                                scene._players_px[idx] = scene.m2px(fx, fy)
                                curr_map[fol_lab] = [fx, fy]
                                changed[fol_lab] = [fx, fy]  # ensure saved this step

        # ---------- Disc change ----------
        disc_pos = [float(scene.disc['pos_m'][0]), float(scene.disc['pos_m'][1])]
        prev_disc = prev_full.get('disc') if prev_full else None
        disc_changed = prev_disc is None or (round(prev_disc[0], 6) != round(disc_pos[0], 6) or round(prev_disc[1], 6) != round(disc_pos[1], 6))

        # ---------- Save sparse entry ----------
        entry = {}
        if changed:
            entry['players'] = changed
        if disc_changed:
            entry['disc'] = disc_pos

        self.data[t] = entry
        # Invalidate cached snapshots at and after this step
        self._snapshot_cache = {k: v for k, v in self._snapshot_cache.items() if k < t}

    def next_step(self):
        self.step = float(int(self.step) + 1)

    def finish_recording(self, scene):
        self.save_step(scene)
        self.max_step = float(max(self.data.keys()) if self.data else 0)
        self.state = 'playback'
        self.step = clamp(self.step, 0, self.max_step)

    def build_snapshot(self, step):
        """Return a full snapshot (players+disc) at integer `step` using cache.

        This composes the baseline step 0 snapshot with subsequent sparse deltas
        and applies follower delays during playback.
        """
        step = int(step)
        if step in self._snapshot_cache:
            return self._snapshot_cache[step]

        # Start from step 0
        base = self.data.get(0, {})
        players = {}
        if 'players' in base:
            for k, v in base['players'].items():
                players[k] = [float(v[0]), float(v[1])]

        disc = None
        if 'disc' in base:
            disc = [float(base['disc'][0]), float(base['disc'][1])]

        # Keep track of when each leader started moving for follower delays
        move_starts = {}

        # First pass: apply leader movements and track their start times
        for s in range(1, step+1):
            entry = self.data.get(s, {})
            for lab, pos in entry.get('players', {}).items():
                # Skip followers - we'll handle them in the second pass
                if any(lab in fmap for fmap in self.temp.get('links', {}).values()):
                    continue
                # Leader moved - record the step
                if lab not in players or players[lab] != pos:
                    move_starts[lab] = s
                players[lab] = [float(pos[0]), float(pos[1])]
            if 'disc' in entry:
                disc = [float(entry['disc'][0]), float(entry['disc'][1])]

        # Second pass: apply follower movements with delays
        if self.temp.get('links'):
            # Rebuild cache if needed
            if self._followers_cache is None:
                self._rebuild_followers_cache()
            
            # Process each leader's followers
            for leader, followers in self._followers_cache.items():
                leader_pos = players.get(leader)
                if leader_pos and leader in move_starts:
                    leader_start = move_starts[leader]
                    for follower, delay in followers:
                        # Apply follower position if enough steps have passed
                        if step >= (leader_start + delay):
                            players[follower] = [float(leader_pos[0]), float(leader_pos[1])]

        snap = {'players': players, 'disc': disc}
        self._snapshot_cache[step] = snap
        return snap

    def update_playback(self, scene, t):
        if not self.data:
            return
        t = clamp(float(t), 0.0, self.max_step)

        # Ensure scene players exist
        if not scene.players:
            scene.players = scene._spawn_players()
            scene._rebuild_px()

        # Get player index map for fast updates
        players_map = getattr(scene, '_player_index_map', {p['label']: idx for idx, p in enumerate(scene.players)})

        i0 = int(math.floor(t))
        i1 = int(math.ceil(t))

        # Get snapshots for interpolation
        snap0 = self.build_snapshot(i0)
        snap1 = None if i0 == i1 else self.build_snapshot(i1)

        if snap1 is None:
            # Exact integer step - use single snapshot
            for lab, pos in snap0.get('players', {}).items():
                idx = players_map.get(lab)
                if idx is not None:
                    scene.players[idx]['pos_m'] = [pos[0], pos[1]]
                    scene._players_px[idx] = scene.m2px(pos[0], pos[1])
            if snap0.get('disc'):
                scene.disc['pos_m'] = [snap0['disc'][0], snap0['disc'][1]]
                scene._disc_px = scene.m2px(snap0['disc'][0], snap0['disc'][1])
            self.step = t
            return

        # Non-integer interpolate
        s0 = self.build_snapshot(i0)
        s1 = self.build_snapshot(i1)
        a = t - i0
        players_map = getattr(scene, '_player_index_map', {p['label']: idx for idx, p in enumerate(scene.players)})

        labs = set(list(s0.get('players', {}).keys()) + list(s1.get('players', {}).keys()))
        for lab in labs:
            p0 = s0.get('players', {}).get(lab)
            p1 = s1.get('players', {}).get(lab)
            if p0 is None and p1 is not None:
                x, y = p1[0], p1[1]
            elif p0 is not None and p1 is None:
                x, y = p0[0], p0[1]
            else:
                x = p0[0] + a*(p1[0]-p0[0])
                y = p0[1] + a*(p1[1]-p0[1])
            idx = players_map.get(lab)
            if idx is not None:
                scene.players[idx]['pos_m'] = [x, y]
                scene._players_px[idx] = scene.m2px(x, y)

        if s0.get('disc') is not None or s1.get('disc') is not None:
            d0 = s0.get('disc') or s1.get('disc')
            d1 = s1.get('disc') or s0.get('disc')
            dx = d0[0] + a*(d1[0]-d0[0])
            dy = d0[1] + a*(d1[1]-d0[1])
            scene.disc['pos_m'] = [dx, dy]
            scene._disc_px = scene.m2px(dx, dy)

        self.step = t


# ============ Scene ============
class Scene:
    def __init__(self, scale):
        self.scale = scale
        # Create empty caches first
        self._geo_px = None
        self._grid_surf = None
        self._font_ticks = None
        self._field_surf = None
        self._players_px = []
        self._disc_px = (0, 0)
        
        # Initialize data structures
        self.players = self._spawn_players()
        self.disc = {"label": "DISC", "team": "Disc", "pos_m": [FIELD_LEN/2, CENTER_Y]}
        
        # Player index map for fast label->index lookup
        self._player_index_map = {}
        
        # Linking and follow simulation state
        self.links = set()           # set of frozenset({label_a,label_b}) (undirected pairs)
        self.link_src = None         # temporary source when creating a link
        self._follow_tasks = []      # [{'follower': idx, 'target': [x,y], 'start': [x,y], 'delay': secs, 'time': 0.0, 'duration': secs}]
        self.follow_delay = 0.35     # seconds before follower starts moving
        self.follow_duration = 0.35  # seconds taken for follower to move to target
        
        # UI selection state
        self._sel = None            # ("player", index) or None for link creation UI
        
        # Initialize geometry and caches
        self._rebuild_px()
        self._rebuild_index_map()

    def _spawn_players(self):
        pad, usable = 3.0, FIELD_WID-6
        rows4 = [pad + usable*i/3 for i in range(4)]
        rows3 = [pad + usable*(i+0.5)/3 for i in range(3)]
        blue = [(6.0,y) for y in rows4] + [(12.0,y) for y in rows3]
        red = [(94.0,y) for y in rows4] + [(88.0,y) for y in rows3]
        players = []
        for i, (x,y) in enumerate(blue, 1):
            players.append({"team": "Blue", "label": f"B{i}", "pos_m": [x,y]})
        for i, (x,y) in enumerate(red, 1):
            players.append({"team": "Red", "label": f"R{i}", "pos_m": [x,y]})
        return players

    def m2px(self, x, y):
        return (MARGIN_L + int(round(x*self.scale)), MARGIN_T + int(round(y*self.scale)))

    def px2m(self, x, y):
        return ((x-MARGIN_L)/self.scale, (y-MARGIN_T)/self.scale)

    def _rebuild_index_map(self):
        """Rebuild player label -> index lookup map"""
        self._player_index_map = {p['label']: idx for idx, p in enumerate(self.players)}

    def _schedule_follow(self, follower_idx, target_pos, delay=None, duration=None):
        """Schedule a follower to move to target position with delay"""
        if follower_idx is None or follower_idx >= len(self.players):
            return
            
        delay = self.follow_delay if delay is None else delay
        duration = self.follow_duration if duration is None else duration
        
        # Remove any existing task for this follower
        self._follow_tasks = [t for t in self._follow_tasks if t['follower'] != follower_idx]
        
        # Add new task with start position
        start_pos = list(self.players[follower_idx]['pos_m'])
        task = {
            'follower': follower_idx,
            'start': start_pos,
            'target': [float(target_pos[0]), float(target_pos[1])],
            'delay': float(delay),
            'time': 0.0,
            'duration': float(duration)
        }
        self._follow_tasks.append(task)
    
    def update(self, dt):
        """Update follow movements (call in main loop). dt is seconds."""
        if not self._follow_tasks:
            return
            
        remaining = []
        for task in self._follow_tasks:
            task['time'] += dt
            if task['time'] >= task['delay']:
                # Start moving after delay
                progress = (task['time'] - task['delay']) / max(0.001, task['duration'])
                if progress >= 1.0:
                    # Finished moving
                    self.players[task['follower']]['pos_m'] = list(task['target'])
                    self._players_px[task['follower']] = self.m2px(*task['target'])
                else:
                    # Interpolate position
                    start = task['start']
                    target = task['target']
                    pos = [
                        start[0] + (target[0] - start[0]) * progress,
                        start[1] + (target[1] - start[1]) * progress
                    ]
                    self.players[task['follower']]['pos_m'] = list(pos)
                    self._players_px[task['follower']] = self.m2px(*pos)
                    remaining.append(task)
            else:
                remaining.append(task)
        self._follow_tasks = remaining

    def _rebuild_px(self):
        s = self.scale
        fw, fh = int(round(FIELD_LEN*s)), int(round(FIELD_WID*s))
        field_rect = pygame.Rect(MARGIN_L, MARGIN_T, fw, fh)
        ezL = pygame.Rect(*self.m2px(0,0), int(round(ENDZONE*s)), fh)
        ezR = pygame.Rect(*self.m2px(GOAL_R,0), int(round(ENDZONE*s)), fh)
        gxL, _ = self.m2px(GOAL_L, 0)
        gxR, _ = self.m2px(GOAL_R, 0)
        top, bot = field_rect.top, field_rect.bottom

        boundary = {
            "Sideline (Left)": (field_rect.left, top, field_rect.left, bot),
            "Sideline (Right)": (field_rect.right, top, field_rect.right, bot),
            "Endline (Top)": (field_rect.left, top, field_rect.right, top),
            "Endline (Bottom)": (field_rect.left, bot, field_rect.right, bot),
        }

        bxL, byC = self.m2px(BRICK_L, CENTER_Y)
        bxR, _ = self.m2px(BRICK_R, CENTER_Y)
        bricks = {"Brick Point (Left)": (bxL,byC), "Brick Point (Right)": (bxR,byC)}

        self._geo_px = {
            "field": field_rect, "ezL": ezL, "ezR": ezR,
            "gL": (gxL,top,gxL,bot), "gR": (gxR,top,gxR,bot),
            "boundary": boundary, "bricks": bricks
        }

        self._players_px = [self.m2px(p["pos_m"][0], p["pos_m"][1]) for p in self.players]
        self._disc_px = self.m2px(*self.disc["pos_m"])

        # Player index map for fast label->index lookup
        self._player_index_map = {p['label']: idx for idx, p in enumerate(self.players)}

        # Build cached static field surface (background, endzones, bricks, border)
        try:
            fw, fh = field_rect.width, field_rect.height
            surf = pygame.Surface((fw, fh), pygame.SRCALPHA)
            surf.fill(COL['field'])
            # endzones (relative)
            ez_w = int(round(ENDZONE * self.scale))
            ezL_rel = pygame.Rect(0, 0, ez_w, fh)
            ezR_rel = pygame.Rect(fw - ez_w, 0, ez_w, fh)
            pygame.draw.rect(surf, COL['ez'], ezL_rel)
            pygame.draw.rect(surf, COL['ez'], ezR_rel)
            # gentle tint overlay to endzones for depth
            tint = pygame.Surface((ezL_rel.width, ezL_rel.height), pygame.SRCALPHA)
            tint.fill((0,0,0,40))
            surf.blit(tint, (ezL_rel.left, ezL_rel.top))
            surf.blit(tint, (ezR_rel.left, ezR_rel.top))
            # goal lines (relative x)
            gxL_rel = gxL - field_rect.left
            gxR_rel = gxR - field_rect.left
            # goal line with faint glow behind
            for w in (6,4):
                pygame.draw.line(surf, COL['line'] if w==4 else (230,230,230), (gxL_rel, 0), (gxL_rel, fh), w)
                pygame.draw.line(surf, COL['line'] if w==4 else (230,230,230), (gxR_rel, 0), (gxR_rel, fh), w)
            # bricks (relative coords)
            for _, (bx, by) in bricks.items():
                rx, ry = bx - field_rect.left, by - field_rect.top
                pygame.draw.circle(surf, COL['brick'], (rx, ry), 6)
                pygame.draw.circle(surf, (0,0,0), (rx, ry), 6, 1)
            # border
            pygame.draw.rect(surf, COL['line'], surf.get_rect(), 3, border_radius=4)
            self._field_surf = surf
        except Exception:
            self._field_surf = None

    def on_scale_change(self, scale, font_ticks):
        if abs(scale-self.scale) < 1e-9:
            return
        self.scale = scale
        self._font_ticks = font_ticks
        self._grid_surf = None
        self._rebuild_px()

    def move_entity(self, tag, nx, ny):
        # Snapping
        gx, gy = round(nx*2)/2, round(ny*2)/2
        dx, dy = nx-gx, ny-gy
        if abs(dx) <= SNAP['hard']:
            nx = gx
        elif abs(dx) <= SNAP['soft']:
            nx -= dx*SNAP['pull']

        if abs(dy) <= SNAP['hard']:
            ny = gy
        elif abs(dy) <= SNAP['soft']:
            ny -= dy*SNAP['pull']

        nx, ny = clamp(nx, 0, FIELD_LEN), clamp(ny, 0, FIELD_WID)

        if tag[0] == "player":
            i = tag[1]
            self.players[i]["pos_m"] = [nx, ny]
            self._players_px[i] = self.m2px(nx, ny)
            
            # Schedule linked followers to move
            leader_label = self.players[i]["label"]
            for pair in self.links:
                if leader_label in pair:
                    # Get the other label in the pair (the follower)
                    other_labels = [label for label in pair if label != leader_label]
                    if other_labels:
                        follower_label = other_labels[0]
                        follower_idx = self._player_index_map.get(follower_label)
                        if follower_idx is not None:
                            # Schedule follower to move to leader's position
                            self._schedule_follow(follower_idx, [nx, ny])
        else:
            self.disc["pos_m"] = [nx, ny]
            self._disc_px = self.m2px(nx, ny)

    def _grid(self, surface, font_ticks):
        if self._grid_surf and self._font_ticks is font_ticks:
            surface.blit(self._grid_surf, (0,0))
            return

        self._font_ticks = font_ticks
        grid = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)

        # Minor lines (softer)
        minor_col = (*COL['grid_minor'][:3], 70)
        for xm in range(int(FIELD_LEN)+1):
            x1, y1 = self.m2px(xm, 0)
            x2, y2 = self.m2px(xm, FIELD_WID)
            pygame.draw.line(grid, minor_col, (x1,y1), (x2,y2))
        for ym in range(int(FIELD_WID)+1):
            x1, y1 = self.m2px(0, ym)
            x2, y2 = self.m2px(FIELD_LEN, ym)
            pygame.draw.line(grid, minor_col, (x1,y1), (x2,y2))

        # Major lines (thicker for 5-marks)
        major_col = (*COL['grid_major'][:3], 180)
        for xm in range(0, int(FIELD_LEN)+1, 5):
            x1, y1 = self.m2px(xm, 0)
            x2, y2 = self.m2px(xm, FIELD_WID)
            pygame.draw.line(grid, major_col, (x1,y1), (x2,y2), 2)
        for ym in range(0, int(FIELD_WID)+1, 5):
            x1, y1 = self.m2px(0, ym)
            x2, y2 = self.m2px(FIELD_LEN, ym)
            pygame.draw.line(grid, major_col, (x1,y1), (x2,y2), 2)

        # Ticks
        for xm in range(0, int(FIELD_LEN)+1, 10):
            tx, _ = self.m2px(xm, 0)
            lbl = font_ticks.render(str(xm), True, COL['tick'])
            grid.blit(lbl, (tx-lbl.get_width()//2, self._geo_px["field"].top+4))
        for ym in range(0, int(FIELD_WID)+1, 10):
            _, ty = self.m2px(0, ym)
            lbl = font_ticks.render(str(ym), True, COL['tick'])
            grid.blit(lbl, (self._geo_px["field"].left+4, ty-lbl.get_height()//2))

        self._grid_surf = grid
        surface.blit(grid, (0,0))

    def draw(self, screen, font_ticks, selected=None, hover=None):
        # If caller doesn't pass selected, use the Scene's internal selection so highlighting still works
        if selected is None:
            selected = self._sel

        g = self._geo_px
        # Blit cached static field surface
        if getattr(self, '_field_surf', None):
            screen.blit(self._field_surf, (g['field'].left, g['field'].top))
        else:
            pygame.draw.rect(screen, COL['field'], g["field"], 0, border_radius=4)
            pygame.draw.rect(screen, COL['ez'], g["ezL"])
            pygame.draw.rect(screen, COL['ez'], g["ezR"])
            for seg in (g["gL"], g["gR"]):
                pygame.draw.line(screen, COL['line'], (seg[0],seg[1]), (seg[2],seg[3]), 4)
            for _, (bx,by) in g["bricks"].items():
                pygame.draw.circle(screen, COL['brick'], (bx,by), 6)
                pygame.draw.circle(screen, (0,0,0), (bx,by), 6, 1)
            pygame.draw.rect(screen, COL['line'], g["field"], 3, border_radius=4)

        self._grid(screen, font_ticks)

        # Draw links between players
        for pair in self.links:
            labels = list(pair)
            idx1 = self._player_index_map.get(labels[0])
            idx2 = self._player_index_map.get(labels[1])
            if idx1 is not None and idx2 is not None:
                x1, y1 = self._players_px[idx1]
                x2, y2 = self._players_px[idx2]
                # Draw link line with glow effect
                pygame.draw.line(screen, (255,255,255,40), (x1,y1), (x2,y2), 4)
                pygame.draw.line(screen, COL['accent'], (x1,y1), (x2,y2), 2)

        # Players
        pr = max(5, int(0.35*self.scale))
        for i, p in enumerate(self.players):
            x, y = self._players_px[i]
            col = COL['blue'] if p["team"]=="Blue" else COL['red']
            is_hover = (hover == ("player", i) and selected is None)
            is_sel = (selected == ("player", i))
            if is_hover:
                pygame.draw.circle(screen, COL['sel'], (x, y), pr+6, 2)
                pygame.draw.circle(screen, (0,0,0), (x, y+1), pr, 1)
            pygame.draw.circle(screen, col, (x, y), pr)
            inner_r = max(1, pr-2)
            pygame.draw.circle(screen, (255,255,255), (x, y), inner_r, 2)
            outline_w = 3 if is_sel else 2
            pygame.draw.circle(screen, (0,0,0), (x, y), pr, outline_w)
            try:
                lbl = font_ticks.render(p.get('label',''), True, (255,255,255))
                screen.blit(lbl, (x - lbl.get_width()//2, y - lbl.get_height()//2))
            except Exception:
                pass

        # Disc
        dx, dy = self._disc_px
        dr = max(5, int(DISC_R*self.scale))
        pygame.draw.circle(screen, (30,30,30), (dx,dy), dr+2)
        pygame.draw.circle(screen, (240,240,240), (dx,dy), dr)
        pygame.draw.circle(screen, (0,0,0), (dx,dy), dr, 2)
        if hover==("disc",None) and selected is None:
            pygame.draw.circle(screen, COL['sel'], (dx,dy), dr+6, 2)
            if self._players_px:
                best = None
                bestd = 1e9
                for px, py in self._players_px:
                    d = math.hypot(px-dx, py-dy)
                    if d < bestd:
                        bestd = d
                        best = (px, py)
                if best is not None:
                    tx, ty = best
                    ax = int(dx + 0.5*(tx-dx))
                    ay = int(dy + 0.5*(ty-dy))
                    pygame.draw.line(screen, (50,50,50), (dx,dy), (ax,ay), 3)
                    pygame.draw.circle(screen, (50,50,50), (ax,ay), 3)

    def pick(self, mx, my):
        dr = max(5, int(DISC_R*self.scale))
        if math.hypot(mx-self._disc_px[0], my-self._disc_px[1]) <= dr+6:
            return ("disc", None)

        pr = max(5, int(0.35*self.scale))
        best, bestd = None, 1e9
        for i, (x,y) in enumerate(self._players_px):
            d = math.hypot(mx-x, my-y)
            if d <= pr+6 and d < bestd:
                best, bestd = ("player", i), d
        return best

    # ---------- NEW: tiny UI glue so you can link by clicking ----------
    # These helpers *do not* force changes to your main loop; they’re optional.
    def handle_click_for_linking(self, mx, my, recording_manager, delay_steps=1):
        """Call this from your mouse-up/click handler (optional).
        1st player click -> highlight. 2nd player click -> link (first=leader, second=follower).
        """
        tag = self.pick(mx, my)
        if tag and tag[0] == "player":
            if self._sel is None:
                # select first (leader)
                self._sel = tag
            else:
                # second click -> follower; build link
                if tag != self._sel:
                    leader_idx = self._sel[1]
                    follower_idx = tag[1]
                    lead_lab = self.players[leader_idx]['label']
                    foll_lab = self.players[follower_idx]['label']
                    recording_manager.link_players(lead_lab, foll_lab, delay_steps=delay_steps)
                # clear selection either way
                self._sel = None
        else:
            # clicked elsewhere -> clear
            self._sel = None

    # If your external UI already manages selection and passes it to draw(),
    # you don't need the helpers above. They are provided for plug-and-play.
    # ----------------------------------------------------------------------

    def hover_text_generic(self, mx, my):
        g = self._geo_px
        for name, (bx,by) in g["bricks"].items():
            if math.hypot(mx-bx, my-by) <= 10:
                return name
        for name, seg in [("Goal Line (Left)", g["gL"]), ("Goal Line (Right)", g["gR"])]:
            if dist_point_seg(mx, my, *seg) <= 6:
                return name
        if g["ezL"].collidepoint(mx, my):
            return "End Zone (Left)"
        if g["ezR"].collidepoint(mx, my):
            return "End Zone (Right)"
        for name, seg in g["boundary"].items():
            if dist_point_seg(mx, my, *seg) <= 6:
                return name
        return None


# ============ CSV I/O ============
def export_csv(scene, filename=None, logger=None):
    name = filename or f"ultimate_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    name = ensure_csv_ext(name)
    path = os.path.join(CONFIG_DIR, name)
    
    if logger:
        logger.log_system_event("export_position", {"filename": name})
    
    try:
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(CSV_HEADERS)
            for p in scene.players:
                w.writerow(["player", p["label"], p["team"], f"{p['pos_m'][0]:.3f}", f"{p['pos_m'][1]:.3f}"])
            x, y = scene.disc["pos_m"]
            w.writerow(["disc", "DISC", "Disc", f"{x:.3f}", f"{y:.3f}"])
        return path
    except Exception as e:
        print("[Export] ERROR:", e)
        return None

def export_strategy(recorder, filename=None, logger=None):
    name = filename or f"strategy_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    name = ensure_csv_ext(name)
    path = os.path.join(CONFIG_DIR, name)
    
    if logger:
        logger.log_system_event("export_strategy", {"filename": name, "total_steps": len(recorder.data)})
    
    try:
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            # Sparse format: step, entity, label, x_m, y_m
            w.writerow(["step", "entity", "label", "x_m", "y_m"])

            for step in sorted(recorder.data.keys()):
                snap = recorder.data[step]
                # players is a dict keyed by label in the new format
                for label, pos in (snap.get('players') or {}).items():
                    try:
                        x, y = float(pos[0]), float(pos[1])
                        w.writerow([step, "player", label, f"{x:.6f}", f"{y:.6f}"])
                    except Exception:
                        continue

                if 'disc' in snap and snap.get('disc') is not None:
                    dx, dy = snap['disc']
                    w.writerow([step, "disc", "DISC", f"{float(dx):.6f}", f"{float(dy):.6f}"])

        if logger:
            logger.log_system_event("export_strategy_success", {"filename": name, "path": path})
        print(f"[Export] Wrote {len(recorder.data)} steps to {path}")
        return path
    except Exception as e:
        if logger:
            logger.log_system_event("export_strategy_error", {"filename": name, "error": str(e)})
        print("[Export] ERROR:", e)
        return None

def import_csv(scene, filename):
    path = os.path.join(CONFIG_DIR, filename)
    players, disc = [], None
    
    try:
        with open(path, "r", newline="") as f:
            for row in csv.DictReader(f):
                ent = row.get("entity", "").lower()
                team = row.get("team", "")
                x = clamp(float(row.get("x_m", 0.0)), 0, FIELD_LEN)
                y = clamp(float(row.get("y_m", 0.0)), 0, FIELD_WID)
                
                if ent=="player" and team in ("Blue", "Red"):
                    players.append({"team": team, "label": row.get("label",""), "pos_m": [x,y]})
                elif ent=="disc":
                    disc = {"label": row.get("label","DISC"), "team": "Disc", "pos_m": [x,y]}
    except Exception as e:
        print("[Import] ERROR:", e)
        return False
    
    if players:
        scene.players = players
    if disc:
        scene.disc = disc
    scene._rebuild_px()
    return True

def import_strategy(recorder, scene, filename, logger=None):
    path = os.path.join(CONFIG_DIR, filename)
    if logger:
        logger.log_system_event("import_strategy", {"filename": filename})
    
    try:
        print(f"[Import Strategy] Reading file: {filename}")
        raw = {}
        with open(path, "r", newline="") as f:
            for row in csv.DictReader(f):
                try:
                    step = int(row.get("step", 0))
                except Exception:
                    continue
                ent = row.get("entity", "").lower()
                label = row.get("label", "")
                try:
                    x = clamp(float(row.get("x_m", 0.0)), 0.0, FIELD_LEN)
                    y = clamp(float(row.get("y_m", 0.0)), 0.0, FIELD_WID)
                except Exception:
                    continue

                if step not in raw:
                    raw[step] = {}
                if ent == "player":
                    if 'players' not in raw[step]:
                        raw[step]['players'] = {}
                    raw[step]['players'][label] = [x, y]
                elif ent == 'disc':
                    raw[step]['disc'] = [x, y]
        
        if raw:
            print(f"[Import Strategy] Successfully imported {len(raw)} steps")
            if logger:
                logger.log_system_event("import_strategy_success", {
                    "filename": filename, "total_steps": len(raw), "max_step": max(raw.keys())
                })

            recorder.data = raw
            recorder.max_step = float(max(raw.keys()))
            recorder.state = 'playback'
            recorder.step = 0.0

            # Rebuild scene base positions
            scene.players = scene._spawn_players()
            scene._rebuild_px()

            # Apply step 0 if present
            if 0 in raw:
                recorder.update_playback(scene, 0.0)
            return True
        else:
            print("[Import Strategy] No valid data found in file")
            return False
    except Exception as e:
        print(f"[Import Strategy] ERROR: {e}")
        return False

# ============ Tooltip ============
def draw_tip(surf, font, text, pos):
    if not text:
        return
    lines = text.split('\n')
    labels = [font.render(ln, True, (240,240,240)) for ln in lines]
    pad = (8,6)
    w = max(lbl.get_width() for lbl in labels) + 2*pad[0]
    h = sum(lbl.get_height() for lbl in labels) + 2*pad[1] + (len(labels)-1)*2
    x, y = pos[0]+14, pos[1]+12
    bg = pygame.Surface((w,h+8), pygame.SRCALPHA)
    pygame.draw.rect(bg, (10,10,12,220), pygame.Rect(0,0,w,h), border_radius=8)
    # small pointer triangle under bubble
    pygame.draw.polygon(bg, (10,10,12,220), [(16,h),(20,h+6),(12,h+6)])
    surf.blit(bg, (x,y))
    yy = y + pad[1]
    for lbl in labels:
        surf.blit(lbl, (x+pad[0], yy))
        yy += lbl.get_height()+2

# ============ Main ============
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Ultimate Field — Optimized")
    clock = pygame.time.Clock()
    linking_mode = False  # Initialize linking mode state
    
    font_tip = pygame.font.SysFont("Arial", 16)
    font_ticks = pygame.font.SysFont("Arial", 12)
    font_ui = pygame.font.SysFont("Arial", 18, bold=True)
    
    logger = UFCLogger()
    scene = Scene(compute_scale(WIN_W, WIN_H))
    is_fullscreen = False

    def toggle_fullscreen():
        nonlocal screen, is_fullscreen, scene, slider, rec_bar_rect
        is_fullscreen = not is_fullscreen
        if is_fullscreen:
            screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
            ww, hh = screen.get_size()
        else:
            screen = pygame.display.set_mode((WIN_W, WIN_H))
            ww, hh = WIN_W, WIN_H

        # recompute scale and rebuild scene geometry
        new_scale = compute_scale(ww, hh)
        scene.on_scale_change(new_scale, font_ticks)

        # update recording bar and slider rects conservatively
        rec_bar_rect.width = ww
        rec_bar_rect.top = hh - UI_BAR_H - RECORD_BAR_H
        rb_y_local = rec_bar_rect.top + 12
        # move slider width to fit new width but keep right-side margin for step label
        slider.rect = pygame.Rect(MARGIN_L, rb_y_local+40, ww-2*MARGIN_L-220, 18)
    
    # UI setup
    btn_w, btn_h, pad = 180, 36, 14
    y_bottom = WIN_H - UI_BAR_H + (UI_BAR_H-btn_h)//2
    
    buttons = {
        'export': make_button((MARGIN_L, y_bottom, btn_w, btn_h), "Export Position", icon='↓'),
        'import': make_button((MARGIN_L + btn_w + pad, y_bottom, btn_w, btn_h), "Import Position", icon='↑'),
        'export_strat': make_button((MARGIN_L + 2*(btn_w + pad), y_bottom, btn_w, btn_h), "Export Strategy", icon='↓'),
        'import_strat': make_button((MARGIN_L + 3*(btn_w + pad), y_bottom, btn_w, btn_h), "Import Strategy", icon='↑'),
        'savelog': make_button((MARGIN_L + 4*(btn_w + pad), y_bottom, btn_w, btn_h), "Save Log", icon='💾'),
    }


    
    # Recording bar
    rec_bar_rect = pygame.Rect(0, WIN_H-UI_BAR_H-RECORD_BAR_H, WIN_W, RECORD_BAR_H)
    rb_y = rec_bar_rect.top + 12
    
    rec_buttons = {
        'record': make_button((MARGIN_L, rb_y, 150, 36), "Record Play", icon='⏺', primary=True),
        'next': make_button((MARGIN_L, rb_y, 130, 36), "Next Step", icon='⏭'),
        'finish': make_button((MARGIN_L+140, rb_y, 170, 36), "Finish Recording", icon='⏹', primary=True),
        'newrec': make_button((MARGIN_L, rb_y, 170, 36), "New Recording", icon='🆕'),
        'linking': make_button((MARGIN_L+320, rb_y, 160, 36), "Linking Mode: Off", icon='🔗'),
    }
    
    # Linking mode state
    linking_mode = False
    
    slider = Slider((MARGIN_L, rb_y+40, WIN_W-2*MARGIN_L-220, 18))
    
    def set_mode_ui(mode):
        rec_buttons['record'].visible = (mode is None)
        rec_buttons['next'].visible = rec_buttons['finish'].visible = (mode == 'recording')
        rec_buttons['newrec'].visible = slider.visible = slider.enabled = (mode == 'playback')
        if mode != 'recording':
            rec_buttons['next'].enabled = rec_buttons['finish'].enabled = False
        else:
            rec_buttons['next'].enabled = rec_buttons['finish'].enabled = True
    
    recorder = RecordingManager()
    set_mode_ui(recorder.state)
    
    toasts = Toasts()
    picker = Picker(font_ui)
    dlg = ExportDialog(font_ui, font_ticks)
    
    dragging = selected = None
    drag_off = (0.0, 0.0)
    mouse = (0, 0)
    
    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                # fullscreen toggle (F11 or 'f')
                if e.key == pygame.K_F11 or e.key == pygame.K_f:
                    toggle_fullscreen()
                    continue
                if e.key in (pygame.K_ESCAPE, pygame.K_q):
                    if picker.visible:
                        picker.visible = False
                    elif dlg.visible:
                        dlg.close()
                    else:
                        running = False
            
            # Dialog priority
            if dlg.visible:
                name = dlg.handle(e)
                if name:
                    if dlg.mode == "position":
                        path = export_csv(scene, name, logger)
                        if path:
                            toasts.show(f"Exported position: {os.path.basename(path)}")
                    else:
                        path = export_strategy(recorder, name, logger)
                        if path:
                            toasts.show(f"Exported strategy: {os.path.basename(path)}")
                continue
            
            if picker.visible:
                picked = picker.handle(e)
                if picked:
                    # process picked filename immediately
                    if picker.mode == "position":
                        if import_csv(scene, picked):
                            toasts.show(f"Imported: {picked}")
                    else:
                        if import_strategy(recorder, scene, picked, logger):
                            slider.set_range(0, recorder.max_step)
                            slider.set_value(0.0)
                            set_mode_ui(recorder.state)
                            toasts.show(f"Imported strategy: {picked}")
                    picker.visible = False
                    # swallow this event
                    continue
                continue
            
            # Slider
            val = slider.handle(e)
            if val is not None and recorder.state == 'playback':
                recorder.update_playback(scene, val)
                logger.log_playback_event("slider_change", val, {"max_step": recorder.max_step})
            
            if e.type == pygame.MOUSEMOTION:
                mouse = e.pos
                for b in list(buttons.values()) + list(rec_buttons.values()):
                    b.update(mouse)
                
                if dragging and recorder.state != 'playback':
                    nx, ny = scene.px2m(*e.pos)
                    scene.move_entity(dragging, nx+drag_off[0], ny+drag_off[1])
            
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                # Recording buttons
                if rec_buttons['record'].clicked(e.pos):
                    recorder.start_recording()
                    set_mode_ui(recorder.state)
                    toasts.show("Recording started. Adjust positions, then press Next Step.")
                    continue
                if rec_buttons['next'].clicked(e.pos) and recorder.state == 'recording':
                    recorder.save_step(scene)
                    recorder.next_step()
                    toasts.show(f"Saved step {int(recorder.step-1)}; now editing step {int(recorder.step)}")
                    continue
                if rec_buttons['finish'].clicked(e.pos) and recorder.state == 'recording':
                    recorder.finish_recording(scene)
                    slider.set_range(0, recorder.max_step)
                    slider.set_value(recorder.step)
                    recorder.update_playback(scene, slider.value)
                    set_mode_ui(recorder.state)
                    toasts.show(f"Recording finished. {int(recorder.max_step)+1} steps recorded.")
                    continue
                if rec_buttons['newrec'].clicked(e.pos) and recorder.state == 'playback':
                    recorder.reset()
                    set_mode_ui(recorder.state)
                    toasts.show("Recording cleared. Ready to record again.")
                    continue
                
                # Main buttons
                if buttons['export'].clicked(e.pos):
                    dlg.mode = "position"
                    dlg.open()
                    continue
                if buttons['import'].clicked(e.pos):
                    picker.mode = "position"
                    picker.visible = True
                    continue
                if buttons['export_strat'].clicked(e.pos) and recorder.data:
                    dlg.mode = "strategy"
                    dlg.open()
                    continue
                if buttons['import_strat'].clicked(e.pos):
                    picker.mode = "strategy"
                    picker.visible = True
                    continue
                if buttons['savelog'].clicked(e.pos):
                    handle_save_log(logger, toasts)
                    continue
                
                # Toggle linking mode
                if rec_buttons['linking'].clicked(e.pos):
                    linking_mode = not linking_mode
                    rec_buttons['linking'].text = f"Linking Mode: {'On' if linking_mode else 'Off'}"
                    scene._sel = None  # Clear any pending selection
                    selected = None
                    toasts.show(f"Linking mode {'enabled' if linking_mode else 'disabled'}", kind='info')
                    continue
                
                # Entity picking & linking
                if recorder.state != 'playback':
                    tag = scene.pick(*e.pos)
                    if tag and tag[0] == "player":
                        if linking_mode:
                            # Linking mode: handle link creation
                            if scene._sel is None:
                                # First click: select leader
                                scene._sel = tag
                                selected = tag
                                toasts.show("Select second player to create link")
                            else:
                                # Second click: create link if different player
                                if tag != scene._sel:
                                    leader_idx = scene._sel[1]
                                    follower_idx = tag[1]
                                    leader = scene.players[leader_idx]["label"]
                                    follower = scene.players[follower_idx]["label"]
                                    scene.links.add(frozenset([leader, follower]))
                                    toasts.show(f"Linked {leader} → {follower}", kind="success")
                                scene._sel = None
                                selected = None
                        else:
                            # Normal mode: allow dragging
                            selected = dragging = tag
                            px, py = scene.players[tag[1]]["pos_m"]
                            mx, my = scene.px2m(*e.pos)
                            drag_off = (px-mx, py-my)
                    else:
                        # Non-player click: clear selection & maybe allow disc drag
                        scene._sel = None
                        if tag:  # Disc click
                            selected = dragging = tag
                            px, py = scene.disc["pos_m"]
                            mx, my = scene.px2m(*e.pos)
                            drag_off = (px-mx, py-my)
            
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                dragging = None
        
        # Update & Render
        dt = clock.get_time() / 1000.0  # Get time since last frame in seconds
        scene.update(dt)  # Update follow movement
        
        screen.fill(COL['bg'])

        # Compute pick once per frame and reuse
        if recorder.state != 'playback':
            pick_for_frame = scene.pick(*mouse)
        else:
            pick_for_frame = None

        scene.draw(screen, font_ticks, selected=selected, hover=pick_for_frame)

        # Recording bar shadow + bar (rounded top corners)
        shadow = pygame.Surface((rec_bar_rect.width, rec_bar_rect.height+6), pygame.SRCALPHA)
        shadow.fill((0,0,0,90))
        screen.blit(shadow, (rec_bar_rect.left, rec_bar_rect.top-4))
        pygame.draw.rect(screen, (24,24,28), rec_bar_rect, border_radius=10)
        pygame.draw.line(screen, (0,0,0), (0, rec_bar_rect.top), (WIN_W, rec_bar_rect.top), 2)

        for b in rec_buttons.values():
            b.draw(screen, font_ui)

        disp = int(round(recorder.step)) if abs(recorder.step-round(recorder.step))<1e-6 else f"{recorder.step:.2f}"
        step_lbl = font_ui.render(f"Step: {disp}", True, (235,235,235))
        screen.blit(step_lbl, (rec_bar_rect.right - step_lbl.get_width() - MARGIN_L, rec_bar_rect.top + 10))

        if recorder.state == 'playback':
            slider.draw(screen, font_ui)

        # Bottom bar (docked square)
        pygame.draw.rect(screen, (28,28,32), (0, WIN_H-UI_BAR_H, WIN_W, UI_BAR_H))
        for b in buttons.values():
            b.draw(screen, font_ui)

        # HUD: legend (top-left)
        lx = MARGIN_L
        ly = MARGIN_T//2
        small = font_ticks
        # legend chips
        chips = [(COL['blue'], 'Offense'), (COL['red'], 'Defense'), ((200,180,40), 'Brick')]
        ox = lx
        for colc, lab in chips:
            pygame.draw.rect(screen, colc, (ox, ly, 12, 12), border_radius=3)
            screen.blit(small.render(lab, True, (220,220,220)), (ox+18, ly-2))
            ox += 18 + small.size(lab)[0] + 10

        # status (top-right)
        status_x = WIN_W - MARGIN_L
        mode = recorder.state or 'Idle'
        steps = f"Steps: {int(recorder.max_step)+1 if recorder.max_step else 0}"
        fps = f"FPS: {int(clock.get_fps())}"
        stext = f"Mode: {mode}  •  {steps}  •  {fps}"
        s_lbl = small.render(stext, True, (200,200,200))
        screen.blit(s_lbl, (status_x - s_lbl.get_width(), ly-2))
        
        # Overlays
        if picker.visible:
            picker.draw(screen)
        if dlg.visible:
            dlg.draw(screen)

        # Tooltip (use pick_for_frame computed earlier)
        if recorder.state != 'playback':
            tag = pick_for_frame
            if tag:
                if tag[0] == "player":
                    p = scene.players[tag[1]]
                    draw_tip(screen, font_tip, f"{p['team']} Player ({p['label']})", mouse)
                else:
                    draw_tip(screen, font_tip, "Frisbee (DISC)", mouse)
            else:
                gtxt = scene.hover_text_generic(*mouse)
                draw_tip(screen, font_tip, gtxt, mouse)
        
        toasts.draw(screen, font_ui)
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
