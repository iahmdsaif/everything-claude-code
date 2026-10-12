--[[
	Builds the Roblox Studio files for the R6 Animation Pack.

	    lune run build_place.luau

	Reads   animations/*.rbxmx  (exported from Blender by r6_export_roblox.py)
	        src/**              (Luau scripts)
	Writes  R6AnimPack.rbxl            a ready-to-open test place
	        install/R6AnimPack.rbxm    module + animations, for ReplicatedStorage
	        install/Animate.rbxm       LocalScript, for StarterCharacterScripts
]]

local fs = require("@lune/fs")
local roblox = require("@lune/roblox")

local Instance = roblox.Instance
local CFrame = roblox.CFrame
local Vector3 = roblox.Vector3
local Color3 = roblox.Color3
local Enum = roblox.Enum

local ORDER = { "Idle", "IdleLook", "Walk", "Run", "Jump", "Fall", "Land", "Climb", "Sit", "ToolHold" }
local ONE_SHOT = { Jump = true, Land = true }

local function new(className: string, props: { [string]: any }, parent: any?)
	local inst = Instance.new(className)
	for key, value in props do
		inst[key] = value
	end
	if parent then
		inst.Parent = parent
	end
	return inst
end

local function script(className: string, name: string, path: string, parent: any)
	return new(className, { Name = name, Source = fs.readFile(path) }, parent)
end

local function loadAnimations()
	local list = {}
	for _, name in ORDER do
		local path = "animations/" .. name .. ".rbxmx"
		assert(fs.isFile(path), "missing " .. path .. " - run the Blender exporter first")
		local sequence = roblox.deserializeModel(fs.readFile(path))[1]
		assert(sequence.ClassName == "KeyframeSequence", path .. " is not a KeyframeSequence")
		table.insert(list, sequence)
	end
	return list
end

local function buildPack(animations)
	local pack = script("ModuleScript", "R6AnimPack", "src/R6AnimPack/init.luau", nil)
	script("ModuleScript", "Config", "src/R6AnimPack/Config.luau", pack)
	local folder = new("Folder", { Name = "Animations" }, pack)
	for _, sequence in animations do
		sequence.Parent = folder
	end
	return pack
end

-- A standard R6 character with Roblox's exact part sizes and Motor6D frames.
local YELLOW = Color3.fromRGB(245, 205, 48)
local BLUE = Color3.fromRGB(13, 105, 172)
local GREEN = Color3.fromRGB(164, 189, 71)

local function makeR6(name: string, at: any)
	local model = new("Model", { Name = name })
	local function part(partName, size, offset, color)
		return new("Part", {
			Name = partName,
			Size = size,
			CFrame = at * offset,
			Color = color,
			TopSurface = Enum.SurfaceType.Smooth,
			BottomSurface = Enum.SurfaceType.Smooth,
			CanCollide = false,
		}, model)
	end
	local root = part("HumanoidRootPart", Vector3.new(2, 2, 1), CFrame.new(), BLUE)
	root.Transparency = 1
	root.Anchored = true
	local torso = part("Torso", Vector3.new(2, 2, 1), CFrame.new(), BLUE)
	local head = part("Head", Vector3.new(2, 1, 1), CFrame.new(0, 1.5, 0), YELLOW)
	local rightArm = part("Right Arm", Vector3.new(1, 2, 1), CFrame.new(1.5, 0, 0), YELLOW)
	local leftArm = part("Left Arm", Vector3.new(1, 2, 1), CFrame.new(-1.5, 0, 0), YELLOW)
	local rightLeg = part("Right Leg", Vector3.new(1, 2, 1), CFrame.new(0.5, -2, 0), GREEN)
	local leftLeg = part("Left Leg", Vector3.new(1, 2, 1), CFrame.new(-0.5, -2, 0), GREEN)
	new("SpecialMesh", { MeshType = Enum.MeshType.Head, Scale = Vector3.new(1.25, 1.25, 1.25) }, head)
	new("Decal", { Name = "face", Texture = "rbxasset://textures/face.png", Face = Enum.NormalId.Front }, head)

	local function motor(motorName, parent, part0, part1, c0, c1)
		new("Motor6D", { Name = motorName, Part0 = part0, Part1 = part1, C0 = c0, C1 = c1, MaxVelocity = 0.1 }, parent)
	end
	local up = CFrame.new(0, 0, 0, -1, 0, 0, 0, 0, 1, 0, 1, 0)
	motor("RootJoint", root, root, torso, up, up)
	motor("Neck", torso, torso, head,
		CFrame.new(0, 1, 0, -1, 0, 0, 0, 0, 1, 0, 1, 0), CFrame.new(0, -0.5, 0, -1, 0, 0, 0, 0, 1, 0, 1, 0))
	motor("Right Shoulder", torso, torso, rightArm,
		CFrame.new(1, 0.5, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0), CFrame.new(-0.5, 0.5, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0))
	motor("Left Shoulder", torso, torso, leftArm,
		CFrame.new(-1, 0.5, 0, 0, 0, -1, 0, 1, 0, 1, 0, 0), CFrame.new(0.5, 0.5, 0, 0, 0, -1, 0, 1, 0, 1, 0, 0))
	motor("Right Hip", torso, torso, rightLeg,
		CFrame.new(1, -1, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0), CFrame.new(0.5, 1, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0))
	motor("Left Hip", torso, torso, leftLeg,
		CFrame.new(-1, -1, 0, 0, 0, -1, 0, 1, 0, 1, 0, 0), CFrame.new(-0.5, 1, 0, 0, 0, -1, 0, 1, 0, 1, 0, 0))

	local humanoid = new("Humanoid", { RigType = Enum.HumanoidRigType.R6 }, model)
	new("Animator", {}, humanoid)
	model.PrimaryPart = root
	return model
end

local function block(name, size, position, color, parent, className: string?)
	return new(className or "Part", {
		Name = name,
		Size = size,
		CFrame = CFrame.new(position),
		Color = color,
		Anchored = true,
		TopSurface = Enum.SurfaceType.Smooth,
		BottomSurface = Enum.SurfaceType.Smooth,
	}, parent)
end

local function buildPlace(animations)
	local game = Instance.new("DataModel")
	local workspace = game:GetService("Workspace")
	local replicated = game:GetService("ReplicatedStorage")
	local starterPlayer = game:GetService("StarterPlayer")
	local starterPack = game:GetService("StarterPack")
	local lighting = game:GetService("Lighting")
	game:GetService("ServerScriptService")
	game:GetService("ServerStorage")
	game:GetService("StarterGui")

	new("Terrain", { Name = "Terrain" }, workspace)
	lighting.ClockTime = 14.5

	starterPlayer.GameSettingsAvatar = Enum.GameAvatarType.R6
	local characterScripts = new("StarterCharacterScripts", { Name = "StarterCharacterScripts" }, starterPlayer)
	local playerScripts = new("StarterPlayerScripts", { Name = "StarterPlayerScripts" }, starterPlayer)
	script("LocalScript", "Animate", "src/Animate.client.luau", characterScripts)
	script("LocalScript", "Gallery", "src/Gallery.client.luau", playerScripts)

	buildPack(animations).Parent = replicated

	-- World ----------------------------------------------------------------
	block("Baseplate", Vector3.new(512, 20, 512), Vector3.new(0, -10, 0), Color3.fromRGB(91, 93, 105), workspace).Locked = true
	new("SpawnLocation", {
		Name = "SpawnLocation",
		Size = Vector3.new(6, 1, 6),
		CFrame = CFrame.new(0, 0.5, 0),
		Anchored = true,
		Duration = 0,
		Color = Color3.fromRGB(99, 95, 98),
		TopSurface = Enum.SurfaceType.Smooth,
	}, workspace)

	-- Gallery: one dummy per animation, facing the spawn.
	local gallery = new("Model", { Name = "AnimationGallery" }, workspace)
	local count = #ORDER
	for i, name in ORDER do
		local x = (i - (count + 1) / 2) * 6
		local dummy = makeR6(name, CFrame.new(x, 3, -22) * CFrame.Angles(0, math.pi, 0))
		dummy:SetAttribute("Animation", name)
		if ONE_SHOT[name] then
			dummy:SetAttribute("OneShot", true)
		end
		dummy.Parent = gallery
		if name == "Sit" then
			block("Bench", Vector3.new(3, 1, 3), Vector3.new(x, 0.5, -21.5), Color3.fromRGB(105, 64, 40), gallery)
		end
	end

	-- Test course for the player's own Animate script.
	local course = new("Folder", { Name = "TestCourse" }, workspace)
	block("ClimbTruss", Vector3.new(2, 28, 2), Vector3.new(24, 14, 6), Color3.fromRGB(163, 162, 165), course, "TrussPart")
	local seat = block("Seat", Vector3.new(2, 1, 2), Vector3.new(-24, 1.5, 6), Color3.fromRGB(105, 64, 40), course, "Seat")
	seat.Name = "TestSeat"
	block("SeatBase", Vector3.new(2, 1, 2), Vector3.new(-24, 0.5, 6), Color3.fromRGB(80, 50, 30), course)
	for step = 1, 14 do
		block("Step" .. step, Vector3.new(2, step, 8), Vector3.new(-14 + step * 2, step / 2, 26), Color3.fromRGB(110, 153, 202), course)
	end
	block("DropPlatform", Vector3.new(10, 14, 10), Vector3.new(20, 7, 26), Color3.fromRGB(110, 153, 202), course)

	-- A plain tool so the hold-tool arm can be tried.
	local tool = new("Tool", { Name = "Test Tool", CanBeDropped = false }, starterPack)
	new("Part", {
		Name = "Handle",
		Size = Vector3.new(0.4, 0.4, 3),
		Color = Color3.fromRGB(200, 200, 205),
		CanCollide = false,
	}, tool)

	return game
end

local animations = loadAnimations()
local place = buildPlace(animations)
fs.writeFile("R6AnimPack.rbxl", roblox.serializePlace(place))

-- Install files for adding the pack to an existing game.
fs.writeDir("install")
fs.writeFile("install/R6AnimPack.rbxm", roblox.serializeModel({ buildPack(loadAnimations()) }))
local animate = Instance.new("LocalScript")
animate.Name = "Animate"
animate.Source = fs.readFile("src/Animate.client.luau")
fs.writeFile("install/Animate.rbxm", roblox.serializeModel({ animate }))

print(("Built R6AnimPack.rbxl and install/ with %d animations"):format(#animations))
