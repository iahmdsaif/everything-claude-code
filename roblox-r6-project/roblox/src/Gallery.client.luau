--[[
	Gallery (LocalScript in StarterPlayer.StarterPlayerScripts)

	Plays every animation in the pack on the row of R6 dummies in
	Workspace.AnimationGallery, so you can compare them side by side while
	play-testing. Each dummy's "Animation" attribute names what it plays.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local pack = require(ReplicatedStorage:WaitForChild("R6AnimPack"))
local gallery = workspace:WaitForChild("AnimationGallery", 10)
if not gallery then
	return
end

local function animate(dummy: Model)
	local name = dummy:GetAttribute("Animation")
	local humanoid = dummy:FindFirstChildOfClass("Humanoid")
	if type(name) ~= "string" or not humanoid then
		return
	end
	local animator = humanoid:FindFirstChildOfClass("Animator") or Instance.new("Animator", humanoid)
	local animation = pack.getAnimation(name)
	if not animation then
		return
	end
	local track = animator:LoadAnimation(animation)
	track.Priority = Enum.AnimationPriority.Core

	-- One-shots (Jump, Land) replay with a pause; loops just loop.
	local oneShot = dummy:GetAttribute("OneShot") == true
	track.Looped = not oneShot
	if not oneShot then
		track:Play(0.2)
		return
	end
	-- Hold the last frame, then fade out and go again - never snap.
	while dummy.Parent do
		track:Play(0.15, 1, 1)
		task.wait(math.max(track.Length - 0.05, 0.1))
		track:AdjustSpeed(0)
		task.wait(0.6)
		track:Stop(0.35)
		task.wait(0.6)
	end
end

for _, dummy in gallery:GetChildren() do
	if dummy:IsA("Model") then
		task.spawn(animate, dummy)
	end
end
