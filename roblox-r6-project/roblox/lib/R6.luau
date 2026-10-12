--[[
	Shared helpers for the Lune build scripts:
	  R6.makeRig(name, cframe, colors?)  -> a standard R6 character model
	  R6.buildPack(root)                 -> the R6AnimPack ModuleScript (+ Config, Animations)
]]

local fs = require("@lune/fs")
local roblox = require("@lune/roblox")

local Instance = roblox.Instance
local CFrame = roblox.CFrame
local Vector3 = roblox.Vector3
local Color3 = roblox.Color3
local Enum = roblox.Enum

local R6 = {}

R6.ORDER = { "Idle", "IdleLook", "Walk", "Run", "Jump", "Fall", "Land", "Climb", "Sit", "ToolHold" }

function R6.new(className: string, props: { [string]: any }, parent: any?)
	local inst = Instance.new(className)
	for key, value in props do
		inst[key] = value
	end
	if parent then
		inst.Parent = parent
	end
	return inst
end
local new = R6.new

local DEFAULT_COLORS = {
	Head = Color3.fromRGB(245, 205, 48),
	Arms = Color3.fromRGB(245, 205, 48),
	Torso = Color3.fromRGB(13, 105, 172),
	Legs = Color3.fromRGB(164, 189, 71),
}

-- A standard R6 character with Roblox's exact part sizes and Motor6D frames.
function R6.makeRig(name: string, at: any, colors: { [string]: any }?)
	local c = colors or DEFAULT_COLORS
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
	local root = part("HumanoidRootPart", Vector3.new(2, 2, 1), CFrame.new(), c.Torso)
	root.Transparency = 1
	root.Anchored = true
	local torso = part("Torso", Vector3.new(2, 2, 1), CFrame.new(), c.Torso)
	local head = part("Head", Vector3.new(2, 1, 1), CFrame.new(0, 1.5, 0), c.Head)
	local rightArm = part("Right Arm", Vector3.new(1, 2, 1), CFrame.new(1.5, 0, 0), c.Arms)
	local leftArm = part("Left Arm", Vector3.new(1, 2, 1), CFrame.new(-1.5, 0, 0), c.Arms)
	local rightLeg = part("Right Leg", Vector3.new(1, 2, 1), CFrame.new(0.5, -2, 0), c.Legs)
	local leftLeg = part("Left Leg", Vector3.new(1, 2, 1), CFrame.new(-0.5, -2, 0), c.Legs)
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

-- The R6AnimPack module with its Config and every exported animation.
-- `root` is the folder that holds src/ and animations/ (the roblox/ folder).
function R6.buildPack(root: string)
	local pack = new("ModuleScript", { Name = "R6AnimPack", Source = fs.readFile(root .. "/src/R6AnimPack/init.luau") })
	new("ModuleScript", { Name = "Config", Source = fs.readFile(root .. "/src/R6AnimPack/Config.luau") }, pack)
	local folder = new("Folder", { Name = "Animations" }, pack)
	for _, name in R6.ORDER do
		local path = root .. "/animations/" .. name .. ".rbxmx"
		assert(fs.isFile(path), "missing " .. path .. " - run the Blender exporter first")
		local sequence = roblox.deserializeModel(fs.readFile(path))[1]
		assert(sequence.ClassName == "KeyframeSequence", path .. " is not a KeyframeSequence")
		sequence.Parent = folder
	end
	return pack
end

return R6
