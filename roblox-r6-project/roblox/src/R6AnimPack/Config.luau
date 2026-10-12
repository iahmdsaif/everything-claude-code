--[[
	R6AnimPack.Config

	After publishing each KeyframeSequence (right-click it -> Save to Roblox),
	paste its number here, e.g. Walk = 1234567890. Leave "" while testing in
	Studio - the pack plays the KeyframeSequences directly there.
]]

return {
	Ids = {
		Idle = "",
		IdleLook = "",
		Walk = "",
		Run = "",
		Jump = "",
		Fall = "",
		Land = "",
		Climb = "",
		Sit = "",
		ToolHold = "",
	},

	-- Roblox's stock R6 animations, used for anything without an id outside Studio.
	Fallback = {
		Idle = 180435571,
		Walk = 180426354,
		Run = 180426354,
		Jump = 125750702,
		Fall = 180436148,
		Climb = 180436334,
		Sit = 178130996,
		ToolHold = 182393478,
	},

	-- Studs the character travels during one loop of each cycle. The Animate
	-- script uses these to set playback speed so feet match ground speed.
	Stride = {
		Walk = 5.0,
		Run = 8.0,
		Climb = 9.0,
	},

	-- Walk fully below WalkFullSpeed, run fully above RunFullSpeed, and a
	-- phase-locked blend of both in between (studs per second).
	WalkFullSpeed = 7,
	RunFullSpeed = 13,

	-- Blend times in seconds (time to ~90% of a change). Blends run through
	-- a critically damped spring, so they ease in AND out - no sudden starts.
	Blend = {
		Ground = 0.35,
		Jump = 0.16,
		Fall = 0.45,
		Land = 0.08, -- fade-in of the landing squash itself
		Climb = 0.3,
		Sit = 0.4,
		IdleLook = 0.8,
	},

	JumpHoldTime = 0.28, -- jump pose plays at least this long before falling takes over
	FallDelay = 0.12, -- ignore tiny drops (stairs, bumps) shorter than this
	LandMinAirTime = 0.35, -- only play the landing after a real fall
	LandMaxSpeed = 6, -- skip the landing squash when sprinting through it
	IdleLookChance = 0.2, -- chance per idle loop to glance around
	ToolFade = 0.2,
}
