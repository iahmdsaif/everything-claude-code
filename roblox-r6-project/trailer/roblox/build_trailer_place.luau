--[[
	Builds DEADAIR_Trailer.rbxl - the Roblox Studio version of the trailer.

	    cd trailer/roblox && lune run build_trailer_place.luau

	Reads trailer_data.json (from export_roblox_trailer.py in Blender) and the
	R6 Animation Pack, and writes a place with the whole town, the tower, the
	lights, the actor with a flashlight, night fog, and the TrailerDirector
	script that plays every shot when you press Play.
]]

local fs = require("@lune/fs")
local roblox = require("@lune/roblox")
local serde = require("@lune/serde")
local R6 = require("../../roblox/lib/R6")

local CFrame = roblox.CFrame
local Vector3 = roblox.Vector3
local Color3 = roblox.Color3
local Enum = roblox.Enum
local new = R6.new

local data = serde.decode("json", fs.readFile("trailer_data.json"))

local function rgb(c)
	return Color3.fromRGB(c[1], c[2], c[3])
end

local function cframe(pos, rot)
	return CFrame.new(pos[1], pos[2], pos[3], rot[1], rot[2], rot[3], rot[4], rot[5], rot[6], rot[7], rot[8], rot[9])
end

local MATERIALS = {
	Asphalt = Enum.Material.Asphalt,
	Concrete = Enum.Material.Concrete,
	Dirt = Enum.Material.Ground,
	Metal = Enum.Material.Metal,
	Rust = Enum.Material.CorrodedMetal,
	["Road Line"] = Enum.Material.SmoothPlastic,
	["Lamp Pole"] = Enum.Material.Metal,
	Crate = Enum.Material.WoodPlanks,
	Facade = Enum.Material.Brick,
}

local function materialFor(name: string)
	for prefix, material in MATERIALS do
		if string.sub(name, 1, #prefix) == prefix then
			return material
		end
	end
	return Enum.Material.SmoothPlastic
end

local function groupFor(name: string): string
	for _, rule in {
		{ "Lamp", "Lamps" }, { "Building", "Buildings" }, { "Roof", "Buildings" },
		{ "Tower", "Tower" }, { "Brace", "Tower" }, { "Ladder", "Tower" }, { "Rung", "Tower" },
		{ "Balcony", "Tower" }, { "Rail", "Tower" }, { "Antenna", "Tower" }, { "Beacon", "Tower" },
		{ "Flood", "Tower" }, { "Dock", "Dock" }, { "Crate", "Dock" }, { "Fence", "Yard" },
	} do
		if string.sub(name, 1, #rule[1]) == rule[1] then
			return rule[2]
		end
	end
	return "Street"
end

-- Tiny deterministic hash for picking lit windows.
local function hash(a: number, b: number, c: number): number
	local h = math.sin(a * 12.9898 + b * 78.233 + c * 37.719) * 43758.5453
	return h - math.floor(h)
end

local function addWindows(building, info, folder, seed)
	-- Windows on the face that looks at the road (x = 0).
	local pos, size = building.CFrame.Position, building.Size
	local towardRoad = if pos.X > 0 then -1 else 1
	local faceX = pos.X + towardRoad * size.X / 2
	local cols = math.floor(size.Z / 4)
	local rows = math.floor((size.Y - 2) / 4)
	local ground = pos.Y - size.Y / 2
	for r = 0, rows - 1 do
		for j = 0, cols - 1 do
			local lit = hash(seed, r, j) > 0.84
			new("Part", {
				Name = "Window",
				Anchored = true,
				CanCollide = false,
				Size = Vector3.new(0.2, 2.0, 2.24),
				CFrame = CFrame.new(faceX + towardRoad * 0.08, ground + 3.2 + r * 4, pos.Z + (j - (cols - 1) / 2) * 4),
				Material = if lit then Enum.Material.Neon else Enum.Material.SmoothPlastic,
				Color = if lit then rgb(info.lit):Lerp(Color3.new(0, 0, 0), 0.25) else Color3.fromRGB(14, 16, 20),
				CastShadow = false,
			}, folder)
		end
	end
end

local function buildTown(workspace)
	local town = new("Model", { Name = "Town" }, workspace)
	local groups = {}
	local function group(name)
		groups[name] = groups[name] or new("Folder", { Name = name }, town)
		return groups[name]
	end
	local byName = {}
	for index, p in data.parts do
		local isCylinder = p.shape == "cylinder"
		local cf = cframe(p.pos, p.rot)
		local size = Vector3.new(p.size[1], p.size[2], p.size[3])
		if isCylinder then -- Roblox cylinders lie along X; stand them up
			cf = cf * CFrame.Angles(0, 0, math.pi / 2)
			size = Vector3.new(p.size[2], p.size[1], p.size[3])
		end
		local part = new("Part", {
			Name = p.name,
			Anchored = true,
			Size = size,
			CFrame = cf,
			Shape = if isCylinder then Enum.PartType.Cylinder else Enum.PartType.Block,
			Material = if p.emit then Enum.Material.Neon else materialFor(p.material or ""),
			Color = rgb(p.emit or p.color),
			TopSurface = Enum.SurfaceType.Smooth,
			BottomSurface = Enum.SurfaceType.Smooth,
		}, group(groupFor(p.name)))
		if string.sub(p.name, 1, 5) == "Bulb" or string.sub(p.name, 1, 8) == "LampHead" then
			part.CastShadow = false
		end
		byName[p.name] = part
		if p.lit then
			addWindows(part, p, group("Windows"), index)
		end
	end

	for _, l in data.lights do
		local color = rgb(l.color)
		local index = string.match(l.name, "%d+")
		if string.sub(l.name, 1, 4) == "Lamp" then
			local head = byName["LampHead" .. index]
			new("PointLight", { Color = color, Range = 48, Brightness = 2.2, Shadows = true }, head)
		elseif l.name == "BeaconLight" then
			new("PointLight", { Color = color, Range = 80, Brightness = 6, Shadows = false }, byName.BeaconLamp)
		elseif l.name == "BeaconLight2" then
			new("PointLight", { Color = color, Range = 45, Brightness = 5, Shadows = true }, byName.BeaconMid)
		elseif l.kind == "SPOT" then
			local pos = Vector3.new(l.pos[1], l.pos[2], l.pos[3])
			local aim = Vector3.new(l.dir[1], l.dir[2], l.dir[3])
			local holder = new("Part", {
				Name = l.name,
				Anchored = true,
				CanCollide = false,
				Transparency = 1,
				Size = Vector3.new(0.5, 0.5, 0.5),
				CFrame = CFrame.lookAt(pos, pos + aim),
			}, group("Tower"))
			new("SpotLight", { Color = color, Range = 60, Brightness = 9, Angle = l.angle + 8,
				Face = Enum.NormalId.Front, Shadows = true }, holder)
		end
	end
	return town
end

local function buildActor(workspace)
	-- Same outfit as the Blender trailer: dark jacket, dark jeans.
	local frame = data.frames[1]
	local at = CFrame.new(frame.root[1], frame.root[2] + 3, frame.root[3])
	local actor = R6.makeRig("Actor", at, {
		Head = Color3.fromRGB(245, 205, 48),
		Arms = Color3.fromRGB(245, 205, 48),
		Torso = Color3.fromRGB(84, 52, 48),
		Legs = Color3.fromRGB(48, 52, 63),
	})
	actor.Parent = workspace
	local arm = actor:FindFirstChild("Right Arm")

	-- Flashlight held at the bottom of the right arm, shining along the arm.
	local torch = new("Part", {
		Name = "Flashlight",
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(1.1, 0.44, 0.44),
		Material = Enum.Material.Metal,
		Color = Color3.fromRGB(25, 25, 28),
		CanCollide = false,
		Massless = true,
		CFrame = arm.CFrame * CFrame.new(0, -1.15, -0.1) * CFrame.Angles(0, 0, math.pi / 2),
	}, actor)
	new("Weld", { Part0 = arm, Part1 = torch, C0 = CFrame.new(0, -1.15, -0.1) * CFrame.Angles(0, 0, math.pi / 2) }, torch)
	local lens = new("Part", {
		Name = "Lens",
		Size = Vector3.new(0.36, 0.06, 0.36),
		Material = Enum.Material.Neon,
		Color = Color3.fromRGB(225, 236, 255),
		CanCollide = false,
		Massless = true,
		CFrame = arm.CFrame * CFrame.new(0, -1.72, -0.1),
	}, actor)
	new("Weld", { Part0 = arm, Part1 = lens, C0 = CFrame.new(0, -1.72, -0.1) }, lens)
	new("SpotLight", { Face = Enum.NormalId.Bottom, Angle = 34, Range = 55, Brightness = 5,
		Color = Color3.fromRGB(220, 232, 255), Shadows = true }, lens)
	-- Visible beam: a Beam between two attachments along the arm.
	local a0 = new("Attachment", { Name = "BeamStart", Position = Vector3.new(0, -1.78, -0.1) }, arm)
	local a1 = new("Attachment", { Name = "BeamEnd", Position = Vector3.new(0, -16, -0.1) }, arm)
	new("Beam", {
		Attachment0 = a0,
		Attachment1 = a1,
		Width0 = 0.4,
		Width1 = 8,
		FaceCamera = true,
		LightEmission = 1,
		LightInfluence = 0,
		Segments = 1,
		Color = roblox.ColorSequence.new(Color3.fromRGB(205, 222, 255)),
		Transparency = roblox.NumberSequence.new({
			roblox.NumberSequenceKeypoint.new(0, 0.55),
			roblox.NumberSequenceKeypoint.new(0.35, 0.8),
			roblox.NumberSequenceKeypoint.new(1, 1),
		}),
	}, arm)
	-- Soft fill (front) and rim (behind) so the actor reads against the dark,
	-- like the Blender lights. HumanoidRootPart faces -Z.
	local root = actor:FindFirstChild("HumanoidRootPart")
	local fill = new("Attachment", { Name = "FillLight", Position = Vector3.new(-2, 3, -6) }, root)
	new("PointLight", { Color = Color3.fromRGB(190, 210, 255), Range = 12, Brightness = 0.9, Shadows = false }, fill)
	local rim = new("Attachment", { Name = "RimLight", Position = Vector3.new(0, 4, 4) }, root)
	new("PointLight", { Color = Color3.fromRGB(140, 175, 255), Range = 10, Brightness = 1.4, Shadows = false }, rim)
	return actor
end

local function buildPlace()
	local game = roblox.Instance.new("DataModel")
	local workspace = game:GetService("Workspace")
	local lighting = game:GetService("Lighting")
	local replicated = game:GetService("ReplicatedStorage")
	local starterPlayer = game:GetService("StarterPlayer")
	local players = game:GetService("Players")
	local soundService = game:GetService("SoundService")
	game:GetService("ServerScriptService")
	game:GetService("ServerStorage")
	game:GetService("StarterGui")
	game:GetService("StarterPack")

	new("Terrain", { Name = "Terrain" }, workspace)
	players.CharacterAutoLoads = false -- the camera belongs to the director
	starterPlayer.GameSettingsAvatar = Enum.GameAvatarType.R6
	local playerScripts = new("StarterPlayerScripts", { Name = "StarterPlayerScripts" }, starterPlayer)
	new("StarterCharacterScripts", { Name = "StarterCharacterScripts" }, starterPlayer)
	new("LocalScript", { Name = "TrailerDirector", Source = fs.readFile("src/TrailerDirector.client.luau") }, playerScripts)

	R6.buildPack("../../roblox").Parent = replicated
	local runtime = {
		fps = data.fps, length = data.length, shots = data.shots, strips = data.strips,
		frames = data.frames, lamps = data.lamps,
	}
	new("ModuleScript", {
		Name = "TrailerData",
		Source = "-- Baked from the Blender trailer by export_roblox_trailer.py\n"
			.. "return game:GetService(\"HttpService\"):JSONDecode([==["
			.. serde.encode("json", runtime) .. "]==])\n",
	}, replicated)

	-- Night, fog and grade.
	lighting.Technology = Enum.Technology.Future
	lighting.ClockTime = 0.3
	lighting.Brightness = 0.6
	lighting.Ambient = Color3.fromRGB(14, 16, 22)
	lighting.OutdoorAmbient = Color3.fromRGB(34, 38, 52)
	lighting.EnvironmentDiffuseScale = 0.25
	lighting.EnvironmentSpecularScale = 0.4
	lighting.ExposureCompensation = 0.35
	lighting.GlobalShadows = true
	new("Atmosphere", {
		Density = 0.44,
		Offset = 0.08,
		Color = Color3.fromRGB(105, 116, 138),
		Decay = Color3.fromRGB(38, 42, 58),
		Glare = 0,
		Haze = 2.4,
	}, lighting)
	new("ColorCorrectionEffect", { Contrast = 0.14, Saturation = -0.25, TintColor = Color3.fromRGB(228, 234, 255) }, lighting)
	new("BloomEffect", { Intensity = 0.9, Size = 30, Threshold = 1.15 }, lighting)

	-- Upload trailer/DEADAIR_Trailer_audio.mp3 and paste its id here to hear the score.
	new("Sound", { Name = "TrailerAudio", SoundId = "", Volume = 1 }, soundService)

	buildTown(workspace)
	buildActor(workspace)
	return game
end

local place = buildPlace()
fs.writeFile("../DEADAIR_Trailer.rbxl", roblox.serializePlace(place))
print(("Built ../DEADAIR_Trailer.rbxl: %d map parts, %d frames of shots"):format(#data.parts, #data.frames))
