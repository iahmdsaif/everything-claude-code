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
local R6 = require("./lib/R6")

local Instance = roblox.Instance
local CFrame = roblox.CFrame
local Vector3 = roblox.Vector3
local Color3 = roblox.Color3
local Enum = roblox.Enum

local ORDER = R6.ORDER
local ONE_SHOT = { Jump = true, Land = true }
local new = R6.new
local makeR6 = R6.makeRig

local function script(className: string, name: string, path: string, parent: any)
	return new(className, { Name = name, Source = fs.readFile(path) }, parent)
end

local function buildPack()
	return R6.buildPack(".")
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

local function buildPlace()
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

	buildPack().Parent = replicated

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

local place = buildPlace()
fs.writeFile("R6AnimPack.rbxl", roblox.serializePlace(place))

-- Install files for adding the pack to an existing game.
fs.writeDir("install")
fs.writeFile("install/R6AnimPack.rbxm", roblox.serializeModel({ buildPack() }))
local animate = Instance.new("LocalScript")
animate.Name = "Animate"
animate.Source = fs.readFile("src/Animate.client.luau")
fs.writeFile("install/Animate.rbxm", roblox.serializeModel({ animate }))

print(("Built R6AnimPack.rbxl and install/ with %d animations"):format(#ORDER))
