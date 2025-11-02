# Ultimate_frisbee_strategy_simulation

## What is This Thing?

Imagine you're an Ultimate Frisbee coach trying to explain a complex play to your team. You could wave your arms around and hope they get it, OR you could use this slick Python application that lets you:

- **Drag and drop players** around a virtual field like you're playing a video game
- **Record entire play sequences** step-by-step, like creating a flip-book animation
- **Scrub through plays** with a slider, watching your strategy unfold in smooth slow-motion
- **Save and share** formations with your team via simple CSV files
<img width="1195" height="762" alt="Screenshot 2025-11-03 at 4 25 27 AM" src="https://github.com/user-attachments/assets/b3625bd9-d3dc-42cc-baae-4d0273a94f48" />

Think of it as "PowerPoint for Ultimate Frisbee" - but way cooler because it's interactive.

## Getting Started (The Boring But Necessary Part)

**What You Need:**
- Python 3.6+ (get it from python.org)
- Pygame library: `pip install pygame`
- The mysterious `ufc_logger` module (referenced in code)
- A computer with a screen (preferably)

**To Launch:**
```bash
python ultimate_field_optimized.py
```

Now let's dive into the good stuff...

---

## The Magic Behind The Curtain ✨

### The Field Is Actually Mathematics

Here's something cool: the entire field exists in **two parallel universes**:

**Universe 1: The Real World (Meters)**
```python
FIELD_LEN, FIELD_WID = 100.0, 37.0  # Actual field dimensions
player_position = [50.5, 18.5]       # Player at 50.5m, 18.5m
```

**Universe 2: The Screen World (Pixels)**
```python
WIN_W, WIN_H = 1200, 780             # Your monitor
player_on_screen = [510, 206]        # Same player in pixels
```

The `Scene` class acts as a **portal between these universes**:

```python
def m2px(self, x, y):  # Meters to Pixels
    return (MARGIN_L + int(x*self.scale), MARGIN_T + int(y*self.scale))

def px2m(self, x, y):  # Pixels to Meters
    return ((x-MARGIN_L)/self.scale, (y-MARGIN_T)/self.scale)
```

**Why split them?** When you resize the window or go fullscreen, only the pixel universe changes. The game logic universe stays stable. Genius! 🧠

---

## The Art of Not Storing Everything: Sparse Recording

Here's where this code gets **really clever**. Let's say you're recording a 50-step play with 14 players. Naive approach:

```
14 players × 50 steps × 2 coordinates = 1,400 numbers to save
```

But watch this magic trick:

### Step 0: Full Snapshot (The Baseline)
```python
{
  'players': {
    'B1': [6.0, 10.5], 'B2': [12.0, 15.5], 'B3': [18.0, 20.0],
    'R1': [94.0, 10.5], 'R2': [88.0, 15.5], ... all 14 players
  },
  'disc': [50.0, 18.5]
}
```

### Step 1: Only What Changed
```python
{
  'players': {'B2': [15.5, 17.0]},  # Only B2 moved!
  'disc': [55.0, 20.0]               # Disc moved
}
```

### Step 2: Again, Just the Movers
```python
{
  'players': {'B2': [20.0, 19.0], 'R1': [90.0, 12.0]},  # Two players
  'disc': [60.0, 22.0]
}
```

**The Result?** Instead of 1,400 numbers, you might only save ~200-300. That's an **85% reduction**! 📉

### But Wait, How Do We Play It Back?

This is the clever part. The `build_snapshot()` method reconstructs any step on-demand:

```python
def build_snapshot(self, step):
    # Start with step 0 (everyone's positions)
    positions = copy_of_step_0
    
    # Apply changes from step 1, 2, 3... up to target step
    for s in range(1, step+1):
        for player_who_moved in step[s]:
            positions[player_who_moved] = new_position
    
    return positions
```

It's like **git commits** for frisbee positions! Each step is a delta, and we reconstruct the full state by applying patches.

**Bonus:** The reconstruction is **cached**, so scrubbing the slider back and forth is smooth as butter. 🧈

---

## The Snapping System: Making You Look Coordinated

Ever try to position something *exactly* on a grid with a mouse? It's frustrating! This code has a **three-tier magnetic snapping system**:

```python
# Step 1: Find nearest half-meter grid point
gx = round(nx * 2) / 2  # Snaps to 0, 0.5, 1.0, 1.5, 2.0...

# Step 2: How far off are we?
dx = nx - gx

# Step 3: Apply magnetic force based on distance
if abs(dx) <= 0.2:        # CLOSE (within 20cm)
    nx = gx               # 🧲 SNAP! Lock exactly to grid
elif abs(dx) <= 0.6:      # NEARBY (within 60cm)
    nx -= dx * 0.6        # 🧲~ Gentle pull toward grid (60% force)
else:                     # FAR (over 60cm)
    # Let them move freely
```

**The Experience:**
- When you're close to a grid line, your player "clicks" into place
- When you're kinda close, you feel a gentle tug toward alignment
- When you're far away, you have complete freedom

It's like the field has **weak gravity wells** at every half-meter mark. Subtle but makes the tool feel professional.

---

## The Visual Polish: Why This Doesn't Look Like a School Project

### 1. The Cached Field Surface (Speed Hack)

The field background never changes, right? So why redraw it 60 times per second?

```python
# Draw ONCE during initialization
self._field_surf = pygame.Surface((width, height))
self._field_surf.fill(GRASS_GREEN)
draw_endzones_on(self._field_surf)
draw_goal_lines_on(self._field_surf)
draw_brick_marks_on(self._field_surf)

# Then every frame, just:
screen.blit(self._field_surf, (0, 0))  # FAST!
```

Instead of 100+ drawing operations per frame, it's now **one blit operation**. This is why the app runs at 60 FPS even on a potato laptop. 🥔

### 2. The Hover Effects (Feel The Love)

When you hover over a player:

```python
if is_hover:
    # Draw a white halo (selection preview)
    pygame.draw.circle(screen, WHITE, (x, y), radius+6, 2)
    
    # Draw a subtle drop shadow (makes it look "lifted")
    pygame.draw.circle(screen, BLACK, (x, y+1), radius, 1)
```

**The result?** The player appears to **lift off the field** slightly when you hover. It's a tiny detail but makes the UI feel alive. ✨

### 3. The Disc's Smart Arrow

When you hover over the disc, it draws an arrow toward the nearest player:

```python
# Find closest player
nearest_player = min(players, key=lambda p: distance(disc, p))

# Draw arrow pointing halfway there
arrow_endpoint = midpoint(disc, nearest_player)
pygame.draw.line(screen, GREY, disc, arrow_endpoint, 3)
pygame.draw.circle(screen, GREY, arrow_endpoint, 3)  # Arrowhead
```

**Why?** It gives you context - "Oh, if I pass right now, it's going to Blue 3." Small UX detail, big impact on usability. 🎯

---

## The Recording Workflow: A State Machine Story

Think of the app as having multiple **personalities** (states):

### 😴 Idle Mode
- Just chilling, no recording
- You can drag players around
- "Record Play" button is glowing, tempting you...

### 🔴 Recording Mode
```python
recorder.state = 'recording'
```
- "Record Play" button vanishes
- "Next Step" and "Finish Recording" appear
- Every time you click "Next Step", it saves only what changed
- Field remains interactive - move players freely

**What happens when you click "Next Step":**
```python
def save_step(self, scene):
    # Compare current positions to last step
    for player in scene.players:
        if player.moved_since_last_step():
            save_only_this_player()  # Sparse!
    
    self.step += 1  # Move to next step
```

### ▶️ Playback Mode
```python
recorder.state = 'playback'
```
- Field becomes **read-only** (no more dragging)
- Slider appears with your full recording
- Scrub through smoothly - even between steps!

**The Interpolation Magic:**

When you drag the slider to step 2.3 (not a whole number), it doesn't just snap to step 2 or 3. It **interpolates**:

```python
# Get positions at step 2 and step 3
pos_at_2 = [10.0, 15.0]
pos_at_3 = [15.0, 20.0]

# We're 30% of the way between them
t = 0.3

# Calculate in-between position
x = pos_at_2[0] + 0.3 * (pos_at_3[0] - pos_at_2[0])  # 11.5
y = pos_at_2[1] + 0.3 * (pos_at_3[1] - pos_at_2[1])  # 16.5
```

**Result:** Buttery smooth animation as you scrub. No jerky jumps between steps. 🎬

---

## The File System: CSVs That Make Sense

### Position Export (Simple Mode)
```csv
entity,label,team,x_m,y_m
player,B1,Blue,6.000,10.500
player,B2,Blue,12.000,15.500
player,R1,Red,94.000,10.500
disc,DISC,Disc,50.000,18.500
```

Clean, human-readable, opens in Excel. Perfect for sharing a single formation.

### Strategy Export (Time-Series Mode)
```csv
step,entity,label,x_m,y_m
0,player,B1,6.000000,10.500000
0,player,B2,12.000000,15.500000
0,disc,DISC,50.000000,18.500000
1,player,B2,15.500000,17.000000
1,disc,DISC,55.000000,20.000000
```

**Notice:** Step 1 only lists B2 and the disc - everything else stayed put. This is the sparse format in action! 📊

---

## The UI Components: Small But Mighty

### Toast Notifications (The Non-Annoying Kind)

```python
class Toasts:
    def show(self, text, seconds=2.2, kind='info'):
        self.queue.append((text, time.time() + seconds, kind))
```

These little bubbles appear at the top of the screen:
- 🟢 **Green**: Success ("Formation saved!")
- 🟡 **Yellow**: Warning ("File already exists")
- ⚫ **Grey**: Info ("Recording started")

They **auto-dismiss** after 2.2 seconds (just long enough to read, not so long you get annoyed). They don't block anything. Perfect. ✅

### The File Picker (Better Than A File Dialog)

Instead of using the ugly OS file dialog, this app has a **custom picker**:

```python
class Picker:
    def files(self):
        # List all CSVs
        # Sort by name or date
        # Cache for 1.5 seconds (performance!)
        # Show in a nice scrollable list
```

**Keyboard shortcuts:**
- `N` - Sort by name
- `D` - Sort by date
- `↑/↓` - Scroll
- Click to select
- `ESC` - Cancel

It **feels** like using a professional app. 🎨

### The Export Dialog (Timestamp Magic)

When you export, the filename auto-generates:

```python
self.text = f"ultimate_{time.strftime('%Y%m%d_%H%M%S')}.csv"
# Result: "ultimate_20250103_143022.csv"
```

You can edit it, or just hit Enter to use the default. Never overwrite files by accident! 🛡️

---

## Performance Secrets: The Need For Speed

### Secret #1: Batch Pixel Conversions
```python
# ❌ SLOW: Convert every frame
for player in players:
    x, y = self.m2px(player.pos_m[0], player.pos_m[1])
    draw_player(x, y)

# ✅ FAST: Pre-convert, store, reuse
self._players_px = [self.m2px(p.pos_m) for p in players]
for x, y in self._players_px:
    draw_player(x, y)
```

### Secret #2: Surface Caching
```python
# ❌ SLOW: Redraw grid every frame (200+ draw calls)
for x in range(100):
    pygame.draw.line(...)  # 60 FPS × 200 lines = 12,000 draw calls/sec

# ✅ FAST: Draw once to surface, blit surface every frame
if not self._grid_surf:
    self._grid_surf = pygame.Surface(...)
    draw_all_grid_lines_once(self._grid_surf)
screen.blit(self._grid_surf, (0,0))  # 1 blit = fast!
```

### Secret #3: Smart Cache Invalidation
```python
def on_scale_change(self, new_scale):
    if abs(new_scale - self.scale) < 0.000001:
        return  # No actual change, skip expensive rebuild
    
    self.scale = new_scale
    self._grid_surf = None      # Invalidate grid cache
    self._field_surf = None     # Invalidate field cache
    self._rebuild_px()          # Rebuild pixel positions
```

Only regenerate what actually changed. Lazy evaluation at its finest! 💤

---

## The Button System: More Than Meets The Eye

Buttons have **states and moods**:

```python
class Button:
    self.enabled = True    # Can I be clicked?
    self.visible = True    # Can you see me?
    self.hover = False     # Is mouse over me?
    self.primary = False   # Am I the main action?
```

**Visual feedback:**
```python
if self.primary and self.enabled:
    color = BRIGHT_BLUE        # "Look at me!"
elif self.enabled:
    color = NORMAL_BLUE        # Regular button
else:
    color = GREY               # Disabled (can't click)

if self.hover and self.enabled:
    color = brighten(color)    # Lighten by 8% on hover
```

**Icons using emoji:**
```python
buttons = {
    'record': Button("Record Play", icon='⏺'),
    'next': Button("Next Step", icon='⏭'),
    'finish': Button("Finish", icon='⏹'),
}
```

Modern, fun, and no need for image files! 🎭

---

## Error Handling: Failing Gracefully

The code doesn't crash when things go wrong. Instead:

```python
try:
    with open(filepath, 'r') as f:
        data = csv.reader(f)
        # ... parse data
except FileNotFoundError:
    toasts.show("File not found!", kind='warn')
    logger.log_error("import_failed", "file_not_found", filepath)
except csv.Error:
    toasts.show("Invalid CSV format", kind='warn')
    logger.log_error("import_failed", "corrupt_csv", filepath)
except Exception as e:
    toasts.show("Import failed", kind='warn')
    logger.log_error("import_failed", "unknown", str(e))
```

**Philosophy:** 
- **User sees:** Friendly message in a toast
- **Developer sees:** Detailed error in log file
- **App does:** Keeps running, doesn't crash

This is **production-grade error handling**. 🛡️

---

## The Coordinate Clamp: Your Safety Net

Every position input gets **clamped** to valid field boundaries:

```python
def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))

# Usage:
x = clamp(x, 0, FIELD_LEN)  # Keep between 0 and 100 meters
y = clamp(y, 0, FIELD_WID)  # Keep between 0 and 37 meters
```

**Why?** 
- Prevents players from being dragged off the field
- Handles corrupted CSV files (positions of 999999)
- Makes the code **defensive** - it expects bad input

**Example:**
```python
# User drags player to (-50, 200) somehow
x = clamp(-50, 0, 100)   # Returns 0
y = clamp(200, 0, 37)    # Returns 37
# Player ends up at corner (0, 37) instead of crashing
```

---

## The Event Priority System: Who Gets To Handle This Click?

Events are handled in **strict priority order**:

```python
# Priority 1: MODAL DIALOGS (blocks everything)
if dialog.visible:
    dialog.handle(event)
    continue  # Skip all other handlers

# Priority 2: FILE PICKER (blocks field)
if picker.visible:
    picker.handle(event)
    continue

# Priority 3: SLIDER (playback control)
slider.handle(event)

# Priority 4: RECORDING BUTTONS (mode switching)
if record_button.clicked():
    switch_to_recording_mode()
    continue

# Priority 5: FIELD INTERACTION (lowest)
tag = scene.pick(mouse_x, mouse_y)
if tag:
    start_dragging(tag)
```

**Why this order?** You don't want to accidentally drag a player when you're trying to close a dialog. The UI needs to be **predictable**. 🎯

---

## The Fullscreen Toggle: Adaptive Layout

Press `F11` and watch the magic:

```python
def toggle_fullscreen():
    if is_fullscreen:
        screen = pygame.display.set_mode((1200, 780))  # Windowed
    else:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    
    # Recalculate EVERYTHING
    new_width, new_height = screen.get_size()
    new_scale = compute_scale(new_width, new_height)
    
    scene.on_scale_change(new_scale)  # Rebuild field
    slider.rect.width = new_width - 2*MARGIN  # Resize slider
    # ... reposition all UI elements
```

**The result:** The field **scales** to fill your screen, maintaining aspect ratio. All UI elements **reflow** to fit. No black bars, no clipping. 🖥️

---

## Real-World Usage Scenarios

### Scenario 1: Teaching A Play to Newbies

1. Set up offensive formation (vertical stack)
2. Click "Record Play"
3. Show initial handler position
4. Next Step: Show first cut (B2 goes deep)
5. Next Step: Show continuation (B3 fills space)
6. Next Step: Show dump option (B1 comes back)
7. Finish Recording
8. Scrub through with slider while explaining
9. Export and send to team Slack

**Total time:** 3 minutes. **Impact:** Everyone understands the play visually. ✅

### Scenario 2: Analyzing Tournament Footage

1. Watch game video
2. Pause at interesting play
3. Import your team's default formation
4. Drag players to match actual positions
5. Record what happened step-by-step
6. Export as "semifinals_game3_play12.csv"
7. Review later with team

**Result:** You now have a **library** of real plays from tournament footage. 📚

### Scenario 3: Designing New Zone Defense

1. Start with basic cup setup
2. Try moving players to different spots
3. Export position as "zone_variation_1.csv"
4. Try another arrangement
5. Export as "zone_variation_2.csv"
6. Import both later to compare side-by-side (in different app instances)

**Bonus:** The CSV format means you can even open them in Excel and do analysis! 📊

---

## The Hidden Gem: Player Index Mapping

There's a sneaky optimization you might miss:

```python
self._player_index_map = {p['label']: idx for idx, p in enumerate(self.players)}
# Result: {'B1': 0, 'B2': 1, 'R1': 7, ...}
```

**Why?** During playback reconstruction, we need to update specific players by label ('B2'). Without this map:

```python
# ❌ SLOW: Search through all players
for i, player in enumerate(players):
    if player['label'] == 'B2':
        player['pos_m'] = new_position
        break
```

With the map:

```python
# ✅ FAST: Direct lookup
idx = self._player_index_map['B2']
players[idx]['pos_m'] = new_position
```

During playback, this happens **60 times per second** for multiple players. The speedup is **noticeable**. 🚀

---

## The Color Palette: Designed For Clarity

```python
COL = {
    'bg': (18,18,20),          # Almost black (easy on eyes)
    'field': (18,110,45),      # Rich grass green
    'ez': (12,85,35),          # Darker green (endzones)
    'blue': (40,120,255),      # Vibrant blue (offense)
    'red': (255,70,70),        # Bright red (defense)
    'brick': (255,215,0),      # Gold (brick marks)
    'accent': (90,170,240),    # Cool blue (UI highlights)
}
```

**Design principles:**
- **High contrast** between players and field
- **Dark background** reduces eye strain during long sessions
- **Distinct team colors** that work for colorblind users
- **Consistent accent color** for all interactive elements

This isn't random RGB values - it's **designed**. 🎨

---

## The Frame Rate Lock: 60 FPS Magic

```python
clock.tick(60)  # Lock to 60 frames per second
```

**What this does:**
- Calculates how much time has passed since last frame
- Sleeps for the remaining time to hit exactly 16.67ms per frame
- Results in **smooth, consistent animation**

**Without this:**
```python
# Frame 1: Takes 5ms → draws at 200 FPS
# Frame 2: Takes 25ms → draws at 40 FPS
# User sees: Jittery, inconsistent motion 😵
```

**With this:**
```python
# Every frame: Exactly 16.67ms → consistent 60 FPS
# User sees: Buttery smooth animation 😌
```

---

## What Makes This Code "Production Ready"

### ✅ Defensive Programming
- Every file operation wrapped in try-catch
- All user inputs clamped/validated
- Graceful degradation on errors

### ✅ Performance Optimization
- Surface caching for static elements
- Lazy evaluation (only rebuild what changed)
- Smart data structures (sparse recording)

### ✅ User Experience Polish
- Magnetic snapping (feels natural)
- Hover effects (visual feedback)
- Toast notifications (non-intrusive)
- Keyboard shortcuts (power users)

### ✅ Maintainability
- Clear separation of concerns
- Consistent naming conventions
- Well-documented with comments
- Modular architecture (easy to extend)

### ✅ Professional Features
- Fullscreen support
- Custom file picker (better than OS dialogs)
- Event logging for debugging
- CSV format for interoperability

---

## The Bottom Line

This isn't just a "draw some circles on a field" script. It's a **carefully crafted application** with:

- **Smart algorithms** (sparse recording, interpolation)
- **Polished UX** (snapping, hover effects, smooth playback)
- **Professional architecture** (caching, state machines, error handling)
- **Thoughtful design** (color palette, keyboard shortcuts, adaptive layout)

The code demonstrates **intermediate-to-advanced** Python game development patterns. You could learn a semester's worth of UI programming concepts just from studying this one file.

**Most impressively:** It accomplishes all this in a single, readable Python file. No framework bloat, no unnecessary dependencies, just clean Pygame code doing exactly what it needs to do. 🏆

Now go forth and design some killer Ultimate plays! 🥏
