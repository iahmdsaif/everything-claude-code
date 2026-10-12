# R6 Animation Pack (Blender + Roblox Studio)

Smooth, loop-perfect animations for the classic Roblox **R6** character, made in
Blender, plus a Roblox Studio project that plays them. This is a separate project:
it does not touch any other trailer or game folders.

![preview](preview/preview_sheet.png)

## What's inside

| Folder / file | What it is |
| --- | --- |
| `blender/R6_AnimPack.blend` | Open in Blender. R6 rig + 10 editable animations (Action Editor dropdown). |
| `blender/r6_build.py` | Rebuilds the rig and every animation from scratch. |
| `blender/r6_export_roblox.py` | Exports your (edited) Blender animations to Roblox files. |
| `blender/render_preview.py` | Renders the 60 fps preview video. |
| `roblox/R6AnimPack.rbxl` | **Open in Roblox Studio** - test place with everything set up. |
| `roblox/install/` | Two files to drop into your own game. |
| `roblox/animations/` | The animations as Roblox KeyframeSequences (`.rbxmx`). |
| `roblox/src/` | The Luau scripts (Animate, loader, config, gallery). |
| `preview/R6_AnimPack_preview.mp4` | 60 fps preview of the animations. |

### The animations

| Name | Loop | Notes |
| --- | --- | --- |
| Idle | yes | Breathing, weight shift, head drift (4 s) |
| IdleLook | yes | Glances left and right, then settles (8 s, plays randomly) |
| Walk | yes | Feet stay on the floor, arms drag, head stays level |
| Run | yes | Push-off hop, forward lean, arm pump |
| Jump | no | Arms swing up, holds the last pose |
| Fall | yes | Arms up, gentle flutter |
| Land | no | Squash after big drops, hands back to idle |
| Climb | yes | Hand-over-hand, opposite leg steps |
| Sit | yes | Seated with breathing |
| ToolHold | yes | Right arm out (only the arm, so you can walk with it) |

## 1. Try it in Roblox Studio (2 minutes)

1. Open `roblox/R6AnimPack.rbxl` in Roblox Studio.
2. Press **Play**.
3. In front of you is a gallery with one dummy per animation. Walk around with
   your own character to feel the new movement. There is a ladder (climb), a
   seat (sit), stairs up to a high platform (jump off it to see the landing),
   and a test tool in your backpack.

No publishing is needed to test in Studio. The pack plays the animations straight
from `ReplicatedStorage.R6AnimPack.Animations`.

## 2. Put it in your own game

1. Set the game to R6: **Game Settings -> Avatar** (or the **Avatar Settings**
   window in newer Studio) -> avatar type **R6**.
2. In the Explorer, right-click **ReplicatedStorage -> Insert from File...** and pick
   `roblox/install/R6AnimPack.rbxm`.
3. Right-click **StarterPlayer -> StarterCharacterScripts -> Insert from File...** and pick
   `roblox/install/Animate.rbxm`. Because it is named `Animate`, it replaces
   Roblox's default animation script.
4. Press Play to test.

### Before you publish the game

Animations need an id to work in a live game:

1. Open `ReplicatedStorage -> R6AnimPack -> Animations`.
2. Right-click each animation (for example `Walk`) -> **Save to Roblox...** and publish it.
   If the game belongs to a group, publish the animations to that same group.
3. Copy the number you get and paste it into `R6AnimPack -> Config` (for example `Walk = 1234567890,`).

If you forget one, the game falls back to Roblox's stock R6 animation for it
(and warns in the output), so your character never freezes.

## 3. Edit the animations in Blender

1. Open `blender/R6_AnimPack.blend` (Blender 4.4 or newer; made with 5.2).
2. Select **R6 Rig**. In the **Dope Sheet -> Action Editor**, pick an action from the
   dropdown (`R6_Walk`, `R6_Run`, ...).
3. Edit poses or curves like any other animation. The loops stay seamless
   because each loop has a Cycles modifier and Blender's cyclic handles.
4. Open `blender/r6_export_roblox.py` in the **Scripting** tab and click **Run Script**.
   New `.rbxmx` files appear in a `roblox_export` folder next to the `.blend`.
5. In Studio, delete the old animation under `R6AnimPack -> Animations`, then right-click
   `Animations` -> **Insert from File...** and pick the new `.rbxmx` file.

New actions are exported too if you give them the custom property `r6_export = 1`
(copy one of the existing actions to get all the settings).

To rebuild everything from scratch, run `blender/r6_build.py` in the Scripting
tab. It only replaces the `R6 AnimPack` collection and the `R6_*` actions.

## Why it looks smooth

- **Exact R6 joints.** The Blender bones sit on Roblox's real Motor6D pivots
  (R6 shoulders turn at the inner top corner, hips at the outer top corner), so
  Studio shows exactly what Blender shows. This was checked frame by frame with
  Roblox's own CFrame maths: every part matches within 0.000003 studs.
- **No snapping.** Movements are layered curves with overlap and follow-through:
  arms lag the legs, the head trails the body, and the gaze stays level.
- **Seamless loops.** The curve slope matches across every loop seam (within 0.5%).
- **Feet stay on the floor.** R6 has no knees, so a contact solver lifts and
  lowers the body so the lowest corner of the feet touches the ground (walk: within
  0.02 studs, never sinking). Runs add a small hop after each push-off.
- **60 keys per second.** The exporter bakes fast moves at 60 fps with linear
  easing, so Roblox plays back Blender's curves instead of re-easing a few keys.
- **Smart blending in game.** The `Animate` script blends with critically damped
  springs, so changes ease in and out and the total weight always stays at 100%.
  Walk and run play phase-locked and speed up or slow down with your real ground
  speed, so feet don't skate.

## Trailer: DEADAIR teaser

`trailer/DEADAIR_Trailer.mp4` is a 34-second teaser made with this pack: a foggy,
blocky town at night, a dead radio signal, and the R6 character walking, running,
jumping and climbing a radio tower with a flashlight. It ends on dead silence.
The concept is my own take on the name "Deadair", because I couldn't see the
game's files. All the wording is easy to change (see below).

| File | What it is |
| --- | --- |
| `trailer/DEADAIR_Trailer.blend` | The whole scene: town, tower, lights, character, one camera per shot. |
| `trailer/deadair_trailer.py` | Builds that scene from scratch and renders the shots. |
| `trailer/make_audio.py` | Makes the soundtrack (static, drone, footsteps on the real foot contacts, impacts, riser). |
| `trailer/assemble.py` | Adds titles, glitch cuts, grain and sound, and writes the final `.mp4`. |

**Change the title or text:** edit `TITLE`, `SUBTITLE` and `CAPTIONS` at the top of
`trailer/assemble.py`, then run it again. No re-rendering is needed:

```bash
python3 make_audio.py audio.wav
python3 assemble.py frames/ audio.wav DEADAIR_Trailer.mp4
```

**Re-render the shots** (for example after changing the town or cameras), either in
Blender with **Render -> Render Animation** on `DEADAIR_Trailer.blend` (set the output
folder first), or from a terminal:

```bash
blender -b DEADAIR_Trailer.blend --python deadair_trailer.py -- --render frames/
```

Needs Python 3 with `numpy` and `Pillow`, plus `ffmpeg`.

## Settings you can tweak

Everything is in `ReplicatedStorage -> R6AnimPack -> Config`: walk/run blend
speeds, stride lengths, blend times, idle-glance chance, and landing rules.
