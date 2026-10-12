--[[
	Animate (LocalScript in StarterPlayer.StarterCharacterScripts)

	Replaces Roblox's default R6 Animate script with a smooth one:
	  * every pose change is a weighted cross-blend that is updated every
	    frame, so nothing ever snaps between animations
	  * walk and run play together, phase-locked, and blend by speed; their
	    playback rate follows ground speed so the feet don't skate
	  * jump -> fall -> land are timed from the humanoid state, with a real
	    landing squash after big drops
	  * idle occasionally glances around; holding a tool raises the arm
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local character = script.Parent
local humanoid = character:WaitForChild("Humanoid") :: Humanoid
local rootPart = character:WaitForChild("HumanoidRootPart") :: BasePart

if humanoid.RigType ~= Enum.HumanoidRigType.R6 then
	warn("[R6AnimPack] Character is not R6 - set the game's avatar type to R6 (Avatar Settings). Animate disabled.")
	return
end

local pack = require(ReplicatedStorage:WaitForChild("R6AnimPack"))
local config = pack.Config

local animator = humanoid:FindFirstChildOfClass("Animator") or humanoid:WaitForChild("Animator", 5)
if not animator then
	animator = Instance.new("Animator")
	animator.Parent = humanoid
end

-- Base layer (Core priority): exactly one "share" of weight split between these.
local BASE = { "Idle", "IdleLook", "Walk", "Run", "Jump", "Fall", "Climb", "Sit" }
local LOOPED = { Idle = true, IdleLook = true, Walk = true, Run = true, Fall = true, Climb = true, Sit = true }
-- If an animation is unavailable its share of weight goes to a stand-in, so
-- the base layer always adds up to exactly 1.
local STAND_IN = { IdleLook = "Idle", Walk = "Run", Run = "Walk", Jump = "Fall", Fall = "Jump", Climb = "Idle", Sit = "Idle" }

local tracks: { [string]: AnimationTrack } = {}
local weights: { [string]: number } = {}
local velocities: { [string]: number } = {}

local function loadTrack(name: string, priority: Enum.AnimationPriority, looped: boolean): AnimationTrack?
	local animation = pack.getAnimation(name)
	if not animation then
		return nil
	end
	local ok, track = pcall(function()
		return animator:LoadAnimation(animation)
	end)
	if not ok then
		warn(("[R6AnimPack] Failed to load %s: %s"):format(name, tostring(track)))
		return nil
	end
	track.Priority = priority
	track.Looped = looped
	tracks[name] = track
	return track
end

for _, name in BASE do
	loadTrack(name, Enum.AnimationPriority.Core, LOOPED[name] == true)
	weights[name] = 0
	velocities[name] = 0
end
local landTrack = loadTrack("Land", Enum.AnimationPriority.Idle, false)
-- Movement priority: above the landing squash, below a game's own Action anims.
local toolTrack = loadTrack("ToolHold", Enum.AnimationPriority.Movement, true)

weights.Idle = 1
for name, track in tracks do
	if weights[name] ~= nil then
		track:Play(0, math.max(weights[name], 1e-4), 1)
	end
end

-- Exact critically damped spring step: eases in and out, never overshoots a
-- step change, and is frame-rate independent. It is linear, so weights that
-- sum to 1 keep summing to 1 while they blend.
local function spring(x: number, v: number, target: number, blendTime: number, dt: number): (number, number)
	local omega = 3.9 / blendTime
	local decay = math.exp(-omega * dt)
	local offset = x - target
	local temp = (v + omega * offset) * dt
	return target + (offset + temp) * decay, (v - omega * temp) * decay
end

local function smoothstep(a: number, b: number, x: number): number
	local t = math.clamp((x - a) / (b - a), 0, 1)
	return t * t * (3 - 2 * t)
end

local function restart(name: string, speed: number?)
	local track = tracks[name]
	if not track then
		return
	end
	if not track.IsPlaying then
		track:Play(0, math.max(weights[name], 1e-4), speed or 1)
	else
		track:AdjustSpeed(speed or 1)
	end
	track.TimePosition = 0
end

-- State --------------------------------------------------------------------

local mode = "ground" -- ground | jump | fall | climb | sit | none
local modeTime = 0
local airTime = 0
local speed = 0
local idleLook = 0
local idleLookVelocity = 0
local idleLookTarget = 0
local dead = false
local landStopping = false

local function setMode(newMode: string)
	if newMode == mode then
		return
	end
	if newMode == "jump" then
		restart("Jump")
	elseif newMode == "fall" then
		restart("Fall")
	elseif newMode == "climb" and mode ~= "climb" then
		restart("Climb", 0)
	end
	mode = newMode
	modeTime = 0
end

local function playLanding()
	if landTrack and speed < config.LandMaxSpeed then
		landStopping = false
		if landTrack.IsPlaying then
			landTrack.TimePosition = 0
			landTrack:AdjustWeight(1, config.Blend.Land)
		else
			landTrack:Play(config.Blend.Land, 1, 1)
		end
	end
end

humanoid.StateChanged:Connect(function(old, new)
	if new == Enum.HumanoidStateType.Jumping then
		setMode("jump")
		airTime = 0
	elseif new == Enum.HumanoidStateType.Freefall or new == Enum.HumanoidStateType.FallingDown then
		if mode ~= "jump" and mode ~= "fall" then
			airTime = 0
			mode = "airborne" -- wait FallDelay before showing the fall pose
			modeTime = 0
		end
	elseif new == Enum.HumanoidStateType.Climbing then
		setMode("climb")
	elseif new == Enum.HumanoidStateType.Seated then
		setMode("sit")
	elseif new == Enum.HumanoidStateType.Landed
		or new == Enum.HumanoidStateType.Running
		or new == Enum.HumanoidStateType.RunningNoPhysics
		or new == Enum.HumanoidStateType.Swimming
	then
		local wasAir = mode == "jump" or mode == "fall" or mode == "airborne"
		if wasAir and airTime >= config.LandMinAirTime then
			playLanding()
		end
		setMode("ground")
	elseif new == Enum.HumanoidStateType.Dead then
		dead = true
		for _, track in tracks do
			track:Stop(0.3)
		end
	elseif new == Enum.HumanoidStateType.Physics or new == Enum.HumanoidStateType.PlatformStanding
		or new == Enum.HumanoidStateType.Ragdoll
	then
		setMode("none")
	end
end)

-- Idle variety: re-roll whenever the idle loop completes.
if tracks.Idle and tracks.IdleLook then
	tracks.Idle.DidLoop:Connect(function()
		if idleLookTarget == 0 and math.random() < config.IdleLookChance then
			tracks.IdleLook.TimePosition = 0
			idleLookTarget = 1
		end
	end)
	tracks.IdleLook.DidLoop:Connect(function()
		idleLookTarget = 0
		tracks.Idle.TimePosition = 0
	end)
end

-- Tools: raise the right arm while a tool with a handle is equipped.
local function refreshTool()
	if not toolTrack then
		return
	end
	local holding = false
	for _, child in character:GetChildren() do
		if child:IsA("Tool") and child.RequiresHandle and child:FindFirstChild("Handle") then
			holding = true
		end
	end
	if holding and not toolTrack.IsPlaying then
		toolTrack:Play(config.ToolFade, 1, 1)
	elseif not holding and toolTrack.IsPlaying then
		toolTrack:Stop(config.ToolFade)
	end
end
character.ChildAdded:Connect(refreshTool)
character.ChildRemoved:Connect(refreshTool)
refreshTool()

-- Per-frame mixer -----------------------------------------------------------

local function lengthOf(name: string, default: number): number
	local track = tracks[name]
	if track and track.Length > 0 then
		return track.Length
	end
	return default
end

local function step(dt: number)
	if dead or not character.Parent then
		return
	end
	modeTime += dt
	if mode == "jump" or mode == "fall" or mode == "airborne" then
		airTime += dt
	end

	-- Ground speed, smoothed. No stick input means "stand", even on conveyors.
	local velocity = rootPart.AssemblyLinearVelocity
	local rawSpeed = Vector3.new(velocity.X, 0, velocity.Z).Magnitude
	if humanoid.MoveDirection.Magnitude < 0.05 then
		rawSpeed = 0
	end
	rawSpeed = math.min(rawSpeed, humanoid.WalkSpeed * 1.5 + 1)
	speed += (rawSpeed - speed) * (1 - math.exp(-dt / 0.08))

	-- Airborne without a jump (walked off a ledge): wait a moment first.
	if mode == "airborne" and modeTime >= config.FallDelay then
		setMode("fall")
	end
	if mode == "jump" and modeTime >= config.JumpHoldTime
		and humanoid:GetState() == Enum.HumanoidStateType.Freefall
	then
		setMode("fall")
	end

	-- Target weights for the base layer (always sums to 1).
	local target = {}
	for _, name in BASE do
		target[name] = 0
	end
	local blend = config.Blend.Ground
	local effective = mode
	if mode == "airborne" then
		effective = "ground"
	end

	if effective == "ground" or effective == "none" then
		local move = smoothstep(0.3, 2.0, speed)
		local run = smoothstep(config.WalkFullSpeed, config.RunFullSpeed, speed)
		if effective == "none" then
			move = 0
		end
		idleLook, idleLookVelocity = spring(idleLook, idleLookVelocity, idleLookTarget, config.Blend.IdleLook, dt)
		idleLook = math.clamp(idleLook, 0, 1)
		target.Idle = (1 - move) * (1 - idleLook)
		target.IdleLook = (1 - move) * idleLook
		target.Walk = move * (1 - run)
		target.Run = move * run
	elseif effective == "jump" then
		target.Jump = 1
		blend = config.Blend.Jump
	elseif effective == "fall" then
		target.Fall = 1
		blend = config.Blend.Fall
	elseif effective == "climb" then
		target.Climb = 1
		blend = config.Blend.Climb
	elseif effective == "sit" then
		target.Sit = 1
		blend = config.Blend.Sit
	end

	for _, name in BASE do
		if not tracks[name] and target[name] > 0 then
			local standIn = STAND_IN[name]
			target[tracks[standIn] and standIn or "Idle"] += target[name]
			target[name] = 0
		end
	end

	-- Every weight follows the same spring, so the layer never dips below
	-- full weight (which would flash the rest pose).
	local total = 0
	for _, name in BASE do
		local w, v = spring(weights[name], velocities[name], target[name], blend, dt)
		weights[name], velocities[name] = w, v
		if tracks[name] then
			total += math.max(w, 0)
		end
	end
	for _, name in BASE do
		local track = tracks[name]
		if track then
			local w = math.max(weights[name], 0) / math.max(total, 1e-6)
			if w > 1e-3 and not track.IsPlaying then
				track:Play(0, w, 1)
			end
			track:AdjustWeight(math.max(w, 1e-4), 0)
		end
	end

	-- Phase-locked walk/run: one shared cadence, so blending never scuffs.
	local runShare = smoothstep(config.WalkFullSpeed, config.RunFullSpeed, speed)
	local stride = config.Stride.Walk + (config.Stride.Run - config.Stride.Walk) * runShare
	local cadence = math.max(speed, 1.5) / stride -- loops per second
	local walkLen, runLen = lengthOf("Walk", 0.8), lengthOf("Run", 0.5)
	local walk, run = tracks.Walk, tracks.Run
	if walk then
		walk:AdjustSpeed(cadence * walkLen)
	end
	if run then
		run:AdjustSpeed(cadence * runLen)
	end
	if walk and run and walk.IsPlaying and run.IsPlaying then
		if weights.Walk >= weights.Run then
			run.TimePosition = (walk.TimePosition / walkLen) * runLen
		else
			walk.TimePosition = (run.TimePosition / runLen) * walkLen
		end
	end

	-- Jump pose holds its last frame instead of snapping back.
	local jump = tracks.Jump
	if jump and jump.IsPlaying and jump.TimePosition >= jump.Length - 0.02 then
		jump:AdjustSpeed(0)
	end

	-- Climb speed follows how fast we actually move up/down the ladder.
	local climb = tracks.Climb
	if climb and mode == "climb" then
		local climbSpeed = math.abs(velocity.Y)
		climb:AdjustSpeed(climbSpeed / config.Stride.Climb * lengthOf("Climb", 0.8))
	end

	-- Landing fades itself out before it ends so it hands back smoothly.
	if landTrack and landTrack.IsPlaying and not landStopping
		and landTrack.TimePosition >= landTrack.Length - 0.2
	then
		landStopping = true
		landTrack:Stop(0.2)
	end
end

-- PreAnimation runs right before animations are stepped (newer engines).
local ok, preAnimation = pcall(function()
	return RunService.PreAnimation
end)
local event: RBXScriptSignal = if ok and preAnimation then preAnimation else RunService.RenderStepped
event:Connect(step)
