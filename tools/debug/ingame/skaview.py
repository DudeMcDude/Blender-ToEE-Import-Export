# SKA-EXPORT check (local only). TP_AUTOEXEC="import skaview; skaview.start()"  TP_TICK="skaview.tick()"
# Spawns an Ice Lizard (proto 14109) next to the leader and makes it play its attack animation every few seconds.
from toee import *
from utilities import location_to_axis, location_from_axis
import os
MODE = os.getenv('SKAVIEW_MODE', 'attack')
S = {'t': 0, 'liz': None, 'n': 0}
def log(s):
	print "SKAVIEW " + s
def start():
	S['t'] = 0
	log("start")
def tick():
	S['t'] += 1
	t = S['t']
	l = game.leader
	if t == 12:
		game.fade_and_teleport(0, 0, 0, 5007, 485, 486)
		log("teleport")
	if t == 30:
		x, y = location_to_axis(l.location)
		liz = game.obj_create(14109, location_from_axis(x + 3, y - 3))
		if MODE != 'falldown':
			liz.npc_flag_set(ONF_KOS_OVERRIDE)
		else:
			liz.npc_flag_unset(ONF_KOS)
			liz.npc_flag_set(ONF_NO_ATTACK)
			liz.reaction_set(l, 100)
		liz.turn_towards(l)
		S['liz'] = liz
		game.scroll_to(liz)
		log("spawned %s at (%d,%d)" % (liz, x + 3, y - 3))
	if MODE == 'falldown':
		if t > 44 and t % 8 == 0 and S['liz'] != None:
			game.scroll_to(S['liz'])
		if t == 33 and S['liz'] != None:
			game.scroll_to(S['liz'])
			S['liz'].fall_down()
			r = S['liz'].condition_add("Unconscious")
			log("uncon %s" % r)
			log("FALLDOWN")
			log("ATTACK 2")
		if t == 120:
			log("DONE")
		return
	if t > 40 and S['liz'] != None and (t - 40) % 16 == 0 and S['n'] < 6:
		S['n'] += 1
		S['liz'].turn_towards(l)
		game.scroll_to(S['liz'])
		r = S['liz'].anim_goal_push_attack(l, 0, 0, 0)
		log("ATTACK %d r=%s" % (S['n'], r))
	if S['n'] >= 6 and (t - 40) % 16 == 15:
		log("DONE")
