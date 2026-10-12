--[[
	TrailerDirector (LocalScript in StarterPlayer.StarterPlayerScripts)

	Plays the DEADAIR teaser inside Roblox: press Play in Studio and it runs
	every shot - camera moves, the actor's movement and animations, lamps
	flickering and dying, the tower beacon, captions, glitches and the title.
	Press R to replay. Record it with Studio's recorder or any screen recorder.

	The shots come from ReplicatedStorage.TrailerData (baked from the Blender
	trailer, so both versions match). Change the words in TEXT below.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local SoundService = game:GetService("SoundService")
local UserInputService = game:GetService("UserInputService")

local TEXT = {
	title = "DEADAIR",
	subtitle = "COMING SOON TO ROBLOX",
	flash = "IT CAN HEAR YOU",
	captions = {
		{ 0.45, 2.75, "THE LAST BROADCAST ENDED AT 11:59 PM" },
		{ 4.3, 7.2, "BUT SOMETHING IS STILL ON THE AIR" },
		{ 25.75, 27.45, "FIND THE SIGNAL" },
	},
}
local GLITCHES = { { 14.5, 15.0 }, { 27.5, 28.0 } }
local TITLE_START, END_CUT = 28.0, 33.0

local data = require(ReplicatedStorage:WaitForChild("TrailerData"))
local pack = require(ReplicatedStorage:WaitForChild("R6AnimPack"))
local actor = workspace:WaitForChild("Actor")
local town = workspace:WaitForChild("Town")
local player = Players.LocalPlayer
local camera = workspace.CurrentCamera

-- Helpers --------------------------------------------------------------------

local function fade(t: number, a: number, b: number, fadeIn: number, fadeOut: number): number
	return math.clamp(math.min((t - a) / fadeIn, (b - t) / fadeOut), 0, 1)
end

local function spaced(text: string): string
	-- Roblox text has no letter-spacing, so widen with thin spaces.
	local out = {}
	for _, code in utf8.codes(text) do
		table.insert(out, utf8.char(code))
	end
	return table.concat(out, "\u{2009}")
end

local function vec(a): Vector3
	return Vector3.new(a[1], a[2], a[3])
end

-- Actor animation ------------------------------------------------------------

local humanoid = actor:WaitForChild("Humanoid")
local animator = humanoid:FindFirstChildOfClass("Animator") or Instance.new("Animator", humanoid)
local rootPart = actor:WaitForChild("HumanoidRootPart")
local LAYERS = {
	Enum.AnimationPriority.Core, Enum.AnimationPriority.Idle, Enum.AnimationPriority.Movement,
	Enum.AnimationPriority.Action, Enum.AnimationPriority.Action2, Enum.AnimationPriority.Action3,
}
local ONE_SHOT = { Jump = true, Land = true }

local tracks: { [string]: AnimationTrack } = {}
local function track(name: string): AnimationTrack?
	if tracks[name] == nil then
		local animation = pack.getAnimation(name)
		tracks[name] = animation and animator:LoadAnimation(animation) or false
	end
	return tracks[name] or nil
end

-- Flatten the strip list into timed events.
local strips = {}
for _, shot in data.shots do
	for layer, s in data.strips[shot.name] or {} do
		table.insert(strips, {
			anim = s.anim,
			start = s.start,
			stop = math.min(s.stop, shot.stop),
			blendIn = s.blendIn,
			offset = s.offset,
			speed = 1 / s.scale,
			priority = if s.anim == "ToolHold" then Enum.AnimationPriority.Action4 else LAYERS[math.min(layer, #LAYERS)],
		})
	end
end
table.sort(strips, function(x, y)
	return x.start < y.start
end)

-- World effects ----------------------------------------------------------------

local lamps = {}
for name, levels in data.lamps do
	local index = string.match(name, "%d+")
	local head = town:FindFirstChild("LampHead" .. index, true)
	local light = head and head:FindFirstChildOfClass("PointLight")
	if light then
		table.insert(lamps, { head = head, light = light, levels = levels,
			brightness = light.Brightness, color = head.Color })
	end
end

local beacons = {}
for _, entry in { { "BeaconLamp", 0.0 }, { "BeaconMid", 0.5 } } do
	local part = town:FindFirstChild(entry[1], true)
	if part then
		local light = part:FindFirstChildOfClass("PointLight")
		table.insert(beacons, { part = part, light = light, phase = entry[2],
			brightness = light and light.Brightness or 0, color = part.Color })
	end
end

local function beaconLevel(t: number): number
	local u = t % 1.6
	local pulse = if u < 0.7 then math.max(0, math.sin(math.pi * u / 0.7)) else 0
	return 0.04 + 0.96 * pulse ^ 1.5
end

-- Screen overlay ----------------------------------------------------------------

local gui = Instance.new("ScreenGui")
gui.Name = "TrailerGui"
gui.IgnoreGuiInset = true
gui.ResetOnSpawn = false
gui.DisplayOrder = 100
gui.Parent = player:WaitForChild("PlayerGui")

local function frame(name, props, parent)
	local f = Instance.new("Frame")
	f.Name = name
	f.BorderSizePixel = 0
	f.BackgroundColor3 = Color3.new(0, 0, 0)
	for k, v in props do
		f[k] = v
	end
	f.Parent = parent or gui
	return f
end

local function label(name, props, parent)
	local l = Instance.new("TextLabel")
	l.Name = name
	l.BackgroundTransparency = 1
	l.TextColor3 = Color3.fromRGB(235, 235, 235)
	l.FontFace = Font.new("rbxasset://fonts/families/GothamSSm.json", Enum.FontWeight.Medium)
	l.AnchorPoint = Vector2.new(0.5, 0.5)
	for k, v in props do
		l[k] = v
	end
	l.Parent = parent or gui
	return l
end

local blackout = frame("Blackout", { Size = UDim2.fromScale(1, 1), ZIndex = 1 })

-- Static: a coarse grid of grey cells re-rolled every frame.
local staticFrame = frame("Static", { Size = UDim2.fromScale(1, 1), BackgroundTransparency = 1, ZIndex = 2, Visible = false })
local cells = {}
local COLS, ROWS = 64, 36
for y = 0, ROWS - 1 do
	for x = 0, COLS - 1 do
		table.insert(cells, frame("c", {
			Size = UDim2.fromScale(1 / COLS + 0.001, 1 / ROWS + 0.001),
			Position = UDim2.fromScale(x / COLS, y / ROWS),
			ZIndex = 2,
		}, staticFrame))
	end
end

local caption = label("Caption", {
	Size = UDim2.fromScale(1, 0.05),
	Position = UDim2.fromScale(0.5, 0.8),
	TextScaled = true,
	ZIndex = 5,
})
local captionSize = Instance.new("UITextSizeConstraint")
captionSize.MaxTextSize = 26
captionSize.Parent = caption

local flash = label("Flash", {
	Size = UDim2.fromScale(1, 0.09),
	Position = UDim2.fromScale(0.5, 0.5),
	Text = spaced(TEXT.flash),
	TextScaled = true,
	FontFace = Font.new("rbxasset://fonts/families/GothamSSm.json", Enum.FontWeight.Heavy),
	TextColor3 = Color3.new(1, 1, 1),
	ZIndex = 6,
	Visible = false,
})

-- Title card: red glow, three offset copies of the title for the glitch.
local titleCard = frame("TitleCard", { Size = UDim2.fromScale(1, 1), ZIndex = 3, Visible = false })
local glows = {}
for i = 1, 8 do
	local s = 0.18 + i * 0.09
	local g = frame("Glow", {
		Size = UDim2.fromScale(s * 1.6, s),
		Position = UDim2.fromScale(0.5, 0.5),
		AnchorPoint = Vector2.new(0.5, 0.5),
		BackgroundColor3 = Color3.fromRGB(120, 8, 6),
		BackgroundTransparency = 1,
		ZIndex = 3,
	}, titleCard)
	local corner = Instance.new("UICorner")
	corner.CornerRadius = UDim.new(0.5, 0)
	corner.Parent = g
	table.insert(glows, g)
end
local titleFont = Font.new("rbxasset://fonts/families/GothamSSm.json", Enum.FontWeight.Heavy)
local function titleLabel(name, color, z)
	return label(name, {
		Size = UDim2.fromScale(0.8, 0.2),
		Position = UDim2.fromScale(0.5, 0.42),
		Text = spaced(TEXT.title),
		TextScaled = true,
		FontFace = titleFont,
		TextColor3 = color,
		ZIndex = z,
	}, titleCard)
end
local titleRed = titleLabel("TitleRed", Color3.fromRGB(255, 40, 40), 4)
local titleCyan = titleLabel("TitleCyan", Color3.fromRGB(40, 220, 255), 4)
local titleMain = titleLabel("Title", Color3.fromRGB(240, 240, 240), 5)
local rule = frame("Rule", {
	Size = UDim2.fromScale(0, 0.003),
	Position = UDim2.fromScale(0.5, 0.535),
	AnchorPoint = Vector2.new(0.5, 0.5),
	BackgroundColor3 = Color3.fromRGB(215, 20, 12),
	ZIndex = 5,
}, titleCard)
local subtitle = label("Subtitle", {
	Size = UDim2.fromScale(0.6, 0.04),
	Position = UDim2.fromScale(0.5, 0.58),
	Text = spaced(TEXT.subtitle),
	TextScaled = true,
	TextColor3 = Color3.fromRGB(190, 190, 195),
	ZIndex = 5,
}, titleCard)

-- Letterbox (2:1) on top of everything.
frame("BarTop", { Size = UDim2.fromScale(1, 0.0556), ZIndex = 10 })
frame("BarBottom", { Size = UDim2.fromScale(1, 0.0556), Position = UDim2.fromScale(0, 0.9444), ZIndex = 10 })

local hint = label("Hint", {
	Size = UDim2.fromScale(0.4, 0.03),
	Position = UDim2.fromScale(0.5, 0.975),
	Text = "R  -  replay",
	TextScaled = true,
	TextColor3 = Color3.fromRGB(110, 110, 115),
	ZIndex = 11,
	Visible = false,
})

local function setStatic(level: number)
	staticFrame.Visible = level > 0
	if level <= 0 then
		return
	end
	for _, cell in cells do
		local v = math.random()
		cell.BackgroundColor3 = Color3.new(v, v, v)
		cell.BackgroundTransparency = 1 - level * (0.55 + 0.45 * math.random())
	end
end

-- Playback ------------------------------------------------------------------------

local audio = SoundService:FindFirstChild("TrailerAudio")
local clock = 0
local playing = false
local nextStrip = 1
local active = {}

local function sample(t: number)
	local f = t * data.fps + 1e-4 -- don't show the outgoing shot on a cut frame
	local i = math.clamp(math.floor(f), 0, #data.frames - 2)
	local a, b = data.frames[i + 1], data.frames[i + 2]
	return a, b, f - i
end

local function startPlayback()
	for _, t in tracks do
		if t then
			t:Stop(0)
		end
	end
	active = {}
	nextStrip = 1
	clock = 0
	playing = true
	hint.Visible = false
	camera.CameraType = Enum.CameraType.Scriptable
	if audio and audio.SoundId ~= "" then
		audio.TimePosition = 0
		audio:Play()
	end
end

local function updateStrips(t: number)
	for i = #active, 1, -1 do
		local s = active[i]
		if t >= s.stop then
			local tr = track(s.anim)
			if tr then
				tr:Stop(0)
			end
			table.remove(active, i)
		end
	end
	while strips[nextStrip] and t >= strips[nextStrip].start do
		local s = strips[nextStrip]
		nextStrip += 1
		local tr = track(s.anim)
		if tr then
			tr.Priority = s.priority
			tr.Looped = not ONE_SHOT[s.anim]
			tr:Play(s.blendIn > 0 and s.blendIn or 0, 1, s.speed)
			local length = tr.Length > 0 and tr.Length or 1
			tr.TimePosition = if ONE_SHOT[s.anim] then math.min(s.offset, length) else s.offset % length
			table.insert(active, s)
		end
	end
end

local function updateWorld(t: number, a, b, u: number)
	-- Actor
	local cut = a.shot ~= b.shot
	local root = if cut then vec(a.root) else vec(a.root):Lerp(vec(b.root), u)
	local yaw = if cut then a.yaw else a.yaw + (b.yaw - a.yaw) * u
	rootPart.CFrame = CFrame.new(root + Vector3.new(0, 3, 0)) * CFrame.Angles(0, yaw, 0)

	-- Camera
	if a.shot then
		local eye, look, fov = vec(a.eye), vec(a.look), a.fov
		if not cut and b.eye then
			eye = eye:Lerp(vec(b.eye), u)
			look = look:Lerp(vec(b.look), u)
			fov = fov + (b.fov - fov) * u
		end
		camera.CFrame = CFrame.lookAt(eye, eye + look.Unit)
		camera.FieldOfView = fov
	end

	-- Lamps and beacons
	local index = math.clamp(math.floor(t * data.fps) + 1, 1, #data.frames)
	for _, lamp in lamps do
		local level = lamp.levels[index] or 1
		lamp.light.Brightness = lamp.brightness * level
		lamp.head.Color = lamp.color:Lerp(Color3.fromRGB(20, 18, 16), 1 - level)
		lamp.head.Material = if level > 0.3 then Enum.Material.Neon else Enum.Material.SmoothPlastic
	end
	for _, beacon in beacons do
		local level = beaconLevel(t + beacon.phase)
		if beacon.light then
			beacon.light.Brightness = beacon.brightness * level
		end
		beacon.part.Color = Color3.fromRGB(30, 2, 2):Lerp(beacon.color, level)
	end
end

local function updateOverlay(t: number)
	-- Black opening, fade up into shot A, black after the title.
	local first = data.shots[1].start
	local black = 1
	if t >= first and t < TITLE_START then
		black = 1 - math.clamp((t - first) / 0.6, 0, 1)
	end
	blackout.BackgroundTransparency = 1 - black

	local captionText, captionAlpha = "", 0
	for _, c in TEXT.captions do
		if t >= c[1] and t < c[2] then
			captionText, captionAlpha = c[3], fade(t, c[1], c[2], 0.6, 0.5)
		end
	end
	caption.Text = spaced(captionText)
	caption.TextTransparency = 1 - captionAlpha

	-- Glitches, and a two-frame kick on every hard cut.
	local static = 0
	flash.Visible = false
	for i, g in GLITCHES do
		if t >= g[1] and t < g[2] then
			local u = (t - g[1]) / (g[2] - g[1])
			static = if math.floor(u * 15) % 5 == 1 then 0.6 else 1
			if i == 1 and ((u > 0.25 and u < 0.42) or (u > 0.6 and u < 0.7)) then
				static = 0.25
				flash.Visible = true
				flash.Position = UDim2.new(0.5, math.random(-6, 6), 0.5, math.random(-3, 3))
			end
		end
	end
	for k, shot in data.shots do
		if k > 1 and t >= shot.start and t < shot.start + 0.07 then
			static = math.max(static, 0.35)
		end
	end
	setStatic(static)

	-- Title card
	titleCard.Visible = t >= TITLE_START and t < END_CUT
	if titleCard.Visible then
		local u = t - TITLE_START
		local pulse = beaconLevel(u)
		for i, g in glows do
			g.BackgroundTransparency = 1 - (0.05 + 0.08 * pulse) * (1 - i / 9)
		end
		local burst = u < 0.6 or (u > 1 and u % 1.35 < 0.07)
		-- (UDim offsets are whole pixels)
		local amount = math.floor(if u < 0.6 then 14 * (1 - u / 0.6) + 4 else (if burst then 5 else 0))
		titleRed.Position = UDim2.new(0.5, -amount + math.random(-2, 2) * (burst and 1 or 0), 0.42, 0)
		titleCyan.Position = UDim2.new(0.5, amount, 0.42, 0)
		titleRed.Visible, titleCyan.Visible = amount > 0, amount > 0
		titleMain.Visible = not (u < 0.6 and math.random() < 0.35 * (1 - u / 0.6))
		titleMain.Position = UDim2.new(0.5, burst and math.random(-4, 4) or 0, 0.42, 0)
		rule.Size = UDim2.fromScale(math.clamp((u - 0.5) / 0.8, 0, 1) * 0.4, 0.003)
		subtitle.TextTransparency = 1 - math.clamp((u - 1.6) / 0.7, 0, 1)
		setStatic(burst and 0.12 or 0.04)
	end
end

RunService:BindToRenderStep("TrailerDirector", Enum.RenderPriority.Camera.Value + 1, function(dt)
	if not playing then
		return
	end
	clock += dt
	local t = clock
	if t >= data.length then
		playing = false
		blackout.BackgroundTransparency = 0
		titleCard.Visible = false
		setStatic(0)
		hint.Visible = true
		return
	end
	if t >= END_CUT and audio and audio.SoundId ~= "" and audio.IsPlaying then
		audio:Stop() -- the end is dead air
	end
	local a, b, u = sample(t)
	updateStrips(t)
	updateWorld(t, a, b, u)
	updateOverlay(t)
end)

UserInputService.InputBegan:Connect(function(input, processed)
	if not processed and input.KeyCode == Enum.KeyCode.R then
		startPlayback()
	end
end)

-- Give the animations a moment to register, then roll.
for _, s in strips do
	track(s.anim)
end
task.wait(1)
startPlayback()
