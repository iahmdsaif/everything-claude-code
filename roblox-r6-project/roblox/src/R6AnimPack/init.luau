--[[
	R6AnimPack (ModuleScript, lives in ReplicatedStorage)

	Turns an animation name ("Walk", "Run", ...) into an Animation instance.

	Where the id comes from, in order:
	  1. Config.Ids[name]           - your published animation id (live games)
	  2. Animations/<name>          - in Studio only, the KeyframeSequence is
	                                  registered as a temporary id so you can
	                                  play-test without publishing anything
	  3. Config.Fallback[name]      - Roblox's stock R6 animation, so a live game
	                                  never ends up with a frozen character
]]

local KeyframeSequenceProvider = game:GetService("KeyframeSequenceProvider")
local RunService = game:GetService("RunService")

local Config = require(script:WaitForChild("Config"))
local Animations = script:WaitForChild("Animations")

local R6AnimPack = {}
R6AnimPack.Config = Config

local cache: { [string]: Animation | false } = {}
local warnedMissing = false

local function normaliseId(id: any): string?
	if id == nil or id == "" or id == 0 then
		return nil
	end
	local text = tostring(id)
	if string.find(text, "://", 1, true) then
		return text
	end
	return "rbxassetid://" .. text
end

local function resolveId(name: string): string?
	local id = normaliseId(Config.Ids[name])
	if id then
		return id
	end

	local sequence = Animations:FindFirstChild(name)
	if sequence and sequence:IsA("KeyframeSequence") and RunService:IsStudio() then
		local ok, result = pcall(function()
			return KeyframeSequenceProvider:RegisterKeyframeSequence(sequence)
		end)
		if ok then
			return result
		end
		warn(("[R6AnimPack] Could not register '%s' for Studio testing: %s"):format(name, tostring(result)))
	end

	if not warnedMissing then
		warnedMissing = true
		warn("[R6AnimPack] Some animations have no published id yet, using Roblox defaults for them. "
			.. "Publish the KeyframeSequences in ReplicatedStorage.R6AnimPack.Animations and paste the ids "
			.. "into ReplicatedStorage.R6AnimPack.Config.")
	end
	return normaliseId(Config.Fallback[name])
end

function R6AnimPack.getAnimation(name: string): Animation?
	local cached = cache[name]
	if cached ~= nil then
		return cached or nil
	end
	local id = resolveId(name)
	if not id then
		cache[name] = false
		return nil
	end
	local animation = Instance.new("Animation")
	animation.Name = name
	animation.AnimationId = id
	cache[name] = animation
	return animation
end

return R6AnimPack
