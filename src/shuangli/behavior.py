from __future__ import annotations

import random
import time


class IdleMotion:
    """Sparse authored gestures over slow random targets; no fixed repeating clip."""

    CLIPS = {
        'soft_blink': {'ParamEyeLOpen': [(0, 1), (.25, 1), (.44, .08), (.62, .08), (1, 1)],
                       'ParamEyeROpen': [(0, 1), (.25, 1), (.44, .08), (.62, .08), (1, 1)]},
        'blink_twice': {'ParamEyeLOpen': [(0, 1), (.22, 1), (.30, 0), (.39, 1), (.53, 0), (.63, 1), (1, 1)],
                        'ParamEyeROpen': [(0, 1), (.22, 1), (.30, 0), (.39, 1), (.53, 0), (.63, 1), (1, 1)]},
        'glance': {'ParamEyeBallX': [(0, 0), (.22, .65), (.60, .65), (1, 0)],
                   'ParamEyeBallY': [(0, 0), (.30, .18), (.65, .18), (1, 0)]},
        'wing_ruffle': {'ParamWingL': [(0, 0), (.20, 14), (.38, 5), (.58, 11), (1, 0)],
                        'ParamWingR': [(0, 0), (.30, -10), (.48, -3), (.68, -8), (1, 0)],
                        'ParamIdleAhoge': [(0, 0), (.32, 9), (.65, -5), (1, 0)]},
        'tail_curl': {'ParamTail': [(0, 0), (.28, 19), (.60, 16), (.80, -6), (1, 0)],
                      'ParamIdleHairR': [(0, 0), (.45, 8), (.75, -3), (1, 0)]},
        'hair_settle': {'ParamIdleHairL': [(0, 0), (.25, 12), (.52, -6), (.76, 3), (1, 0)],
                        'ParamIdleHairR': [(0, 0), (.34, -9), (.64, 5), (1, 0)],
                        'ParamIdleAhoge': [(0, 0), (.22, -12), (.47, 7), (.73, -3), (1, 0)]},
        'wing_tail': {'ParamWingL': [(0, 0), (.20, 12), (.48, 8), (.70, 0), (1, 0)],
                      'ParamWingR': [(0, 0), (.30, -12), (.54, -8), (.78, 0), (1, 0)],
                      'ParamTail': [(0, 0), (.25, 0), (.55, -16), (.78, 7), (1, 0)]},
    }
    LIMITS = {'ParamTail': 14, 'ParamWingL': 12, 'ParamWingR': 12,
              'ParamIdleAhoge': 14, 'ParamIdleHairL': 12, 'ParamIdleHairR': 12}

    def __init__(self):
        self.random = random.Random()
        self.channels = {}
        self.clip = None
        self.recent = []
        self.next_clip = 0.0
        self.enabled = False

    @staticmethod
    def curve(keys, progress):
        for (left, a), (right, b) in zip(keys, keys[1:]):
            if progress <= right:
                u = min(1, max(0, (progress-left)/(right-left)))
                return a+(b-a)*u*u*(3-2*u)
        return keys[-1][1]

    def values(self, now, *, enabled, quiet, available, cursor_near):
        if not enabled:
            self.enabled = False
            self.clip = None
            self.channels.clear()
            return {ident: 0 for ident in self.LIMITS}
        if not self.enabled:
            self.enabled = True
            self.next_clip = now+self.random.uniform(1.8, 3.5)
        result = {}
        for ident, amplitude in self.LIMITS.items():
            if ident not in available: continue
            channel = self.channels.get(ident)
            if channel is None:
                channel = (now, now+self.random.uniform(1.5, 3), 0,
                           self.random.choice([-1, 1])*self.random.uniform(.55, 1)*amplitude)
            start, end, a, b = channel
            if now >= end:
                direction = (-1 if b > 0 else 1) if self.random.random() < .8 else self.random.choice([-1, 1])
                start, end, a, b = now, now+self.random.uniform(1.8, 4), b, direction*self.random.uniform(.55, 1)*amplitude
            self.channels[ident] = start, end, a, b
            result[ident] = self.curve([(0, a), (1, b)], (now-start)/(end-start))
        if self.clip is None and now >= self.next_clip:
            eligible = [name for name, tracks in self.CLIPS.items()
                       if any(ident in available for ident in tracks)
                       and (name != 'glance' or not cursor_near)]
            choices = [name for name in eligible if name not in self.recent] or eligible
            if choices:
                name = self.random.choice(choices)
                self.recent = (self.recent+[name])[-2:]
                eyes = name in ('soft_blink', 'blink_twice')
                self.clip = (name, now, self.random.uniform(.8, 1.3) if eyes else self.random.uniform(2.8, 5.0),
                             1 if eyes else self.random.choice([-1, 1]), 1 if eyes else self.random.uniform(1.05, 1.3))
            self.next_clip = now+self.random.uniform(8, 15) if quiet else now+self.random.uniform(5, 10)
        if self.clip is not None:
            name, start, duration, direction, strength = self.clip
            progress = (now-start)/duration
            if progress >= 1:
                self.clip = None
                self.next_clip = max(self.next_clip, now+4)
            else:
                for ident, keys in self.CLIPS[name].items():
                    if ident not in available or ident.startswith('ParamEyeBall') and cursor_near: continue
                    value = self.curve(keys, progress)*direction*strength
                    if ident.startswith('ParamEye'):
                        result[ident] = value
                    else:
                        result[ident] = max(-30, min(30, result.get(ident, 0)+value))
        return result


class CompanionBehavior:
    """Low-frequency observations and bounded, silent reaction scheduling."""

    def __init__(self):
        now = time.monotonic()
        self.random = random.Random()
        self.next_observation = 0.0
        self.next_micro = now + self.random.uniform(30, 55)
        self.next_stretch = now + self.random.uniform(65, 90)
        self.next_sit = now + self.random.uniform(30, 45)
        self.cooldowns = {}
        self.rest = 'idle'
        self.near_since = None
        self.near = False
        self.previous_idle = 0.0
        self.previous_cursor = None
        self.last_micro = ''
        self.stroke_distance = 0.0
        self.stroke_until = 0.0
        self.pending_wake_until = 0.0
        self.next_reaction = now + 4
        self.pending = []
        self.recent = []
        self.moving_since = None
        self.active_since = now
        self.next_focus = now + self.random.uniform(75, 120)
        self.next_drowsy = 0.0
        self.hover_region = ''
        self.hover_since = now
        self.hover_motion = 0.0
        self.pet_streak = 0
        self.last_pet = 0.0
        self.flop_due = 0.0

    def queue(self, name, now, delay, lifetime=12):
        self.pending = [item for item in self.pending if item[0] != name]
        self.pending.append((name, now + delay, now + delay + lifetime))
        self.pending = self.pending[-3:]

    def performed(self, name, now, duration):
        """Only accepted clips consume the common gap or schedule a follow-up."""
        self.next_reaction = now + duration + self.random.uniform(4, 7)
        self.recent = (self.recent + [name])[-3:]
        followups = {'stretch': 'relieved', 'wake_up': 'content',
                     'yawn': 'sleepy_nod', 'pat': 'content',
                     'startled': 'relieved', 'settle': 'wing_adjust',
                     'meme_shock': 'relieved', 'meme_smug': 'bashful_smile',
                     'meme_pout': 'relieved', 'meme_tears': 'content',
                     'meme_dizzy': 'settle', 'meme_flop': 'perk_up'}
        if name in followups:
            self.queue(followups[name], now, duration + self.random.uniform(5, 8))

    def interrupted(self):
        self.pending.clear()

    def released(self, now):
        self.interrupted()
        self.next_stretch = min(self.next_stretch, now + 6)

    def landed(self, now, impact=0):
        self.queue('meme_dizzy' if impact > 650 else 'relieved', now, .7 if impact > 650 else 5)

    def reaction(self, name, now, cooldown):
        if now < self.cooldowns.get(name, 0):
            return None
        self.cooldowns[name] = now + cooldown
        return name

    def observe(self, now, idle, cursor, bounds, *, blocked, enabled, quiet,
                moving, explicit_sleep, can_pet, mood=0, reaction_busy=False):
        if now < self.next_observation:
            return None
        self.next_observation = now + .25
        returned = self.previous_idle >= 120 and idle < 2
        flopped = self.previous_idle < 45 <= idle < 90
        if returned:self.pending_wake_until = now + 8
        self.previous_idle = idle
        old_rest = self.rest
        self.rest = 'sleep' if idle >= 600 else 'drowsy' if idle >= 180 else 'sit' if idle >= 90 else 'idle'
        x, y, width, height = bounds
        cx, cy = cursor
        hover_age = now - self.near_since if self.near_since is not None else 0
        near = x - width * .35 <= cx <= x + width * 1.35 and y - height * .25 <= cy <= y + height
        entered = near and not self.near
        left = not near and self.near and self.near_since is not None and now - self.near_since >= 3
        if entered:
            self.near_since = now
        if not near:
            self.near_since = None
        self.near = near
        previous = self.previous_cursor
        self.previous_cursor = cursor
        if idle >= 15:
            self.active_since = now
        if moving:
            if self.moving_since is None:self.moving_since = now
        elif self.moving_since is not None:
            if now - self.moving_since >= 4 and not blocked:
                self.queue('settle', now, 2)
            self.moving_since = None
        self.pending = [item for item in self.pending if item[2] > now]
        if not enabled or explicit_sleep:
            self.interrupted()
        if blocked or not enabled or explicit_sleep:
            self.stroke_distance = 0
            self.next_micro = max(self.next_micro, now + 8)
            return None
        if self.pending_wake_until > now or old_rest in ('sleep', 'drowsy') and self.rest == 'idle':
            self.pending_wake_until = 0
            self.next_micro = now + self.random.uniform(30, 55)
            return self.reaction('wake_up', now, 45)
        if old_rest == 'sit' and self.rest == 'idle':
            self.queue('perk_up', now, 1)
        if entered and not moving:
            distance = ((cx - previous[0]) ** 2 + (cy - previous[1]) ** 2) ** .5 if previous else 0
            self.queue('meme_shock' if distance > width * 1.5 else 'notice', now, 0, 7)
        if left and not moving:
            self.queue('meme_tears' if hover_age >= 12 else 'glance_away', now, .8)
        if flopped and not moving and now >= self.flop_due:
            self.queue('meme_flop',now,0,25)
            self.flop_due=now+180
        # Independent zones react to dwelling and rubbing, without opening a menu.
        region = ''
        if x <= cx <= x + width and y <= cy <= y + height and can_pet:
            nx, ny = (cx-x)/width, (cy-y)/height
            if ny < .25 and (nx < .3 or nx > .65):region = 'horn'
            elif .24 <= nx <= .66 and .1 <= ny <= .4:region = 'head'
            elif .26 <= nx <= .63 and .39 < ny <= .53:region = 'cheek'
            elif .54 <= ny <= .73 and (nx < .23 or nx > .75):region = 'wing'
            elif nx > .73 and .72 < ny <= .95:region = 'tail'
        if blocked or moving:region = ''
        if region != self.hover_region:
            self.hover_region = region;self.hover_since = now;self.hover_motion = 0
        elif region and previous:
            distance = ((cx-previous[0])**2+(cy-previous[1])**2)**.5
            if distance < width*.5:self.hover_motion += distance
            if now-self.hover_since >= 1.4 and region != 'head':
                name = {'horn':'meme_shock', 'cheek':'bashful_smile',
                        'wing':'wing_adjust', 'tail':'tail_flick'}[region]
                if self.hover_motion > width*.8:name = 'meme_pout'
                self.queue(name,now,0,6)
                self.hover_since = now + 12;self.hover_motion = 0
        if reaction_busy or now < self.next_reaction:
            return None
        if self.rest == 'sleep':
            self.interrupted()
            return None
        if not moving:
            for item in self.pending[:]:
                name, due, expiry = item
                sleepy = name == 'sleepy_nod'
                if sleepy != (self.rest == 'drowsy') or self.rest == 'sit':
                    self.pending.remove(item)
                    continue
                if now >= due:
                    self.pending.remove(item)
                    reaction = self.reaction(name, now, {'notice':22, 'startled':90, 'glance_away':35}.get(name,20))
                    if reaction:return reaction
        if self.rest == 'drowsy':
            if now >= self.next_drowsy:
                self.next_drowsy = now + 100
                return self.random.choice(['yawn', 'sleepy_nod'])
            return None
        if self.rest == 'sit':
            return None
        # Cursor strokes need actual movement over the head; pet motion is excluded.
        head = x + width * .24 <= cx <= x + width * .66 and y + height * .10 <= cy <= y + height * .40
        if head and previous and can_pet and not moving:
            distance = ((cx - previous[0]) ** 2 + (cy - previous[1]) ** 2) ** .5
            if now > self.stroke_until:
                self.stroke_distance = 0
            if 2 <= distance <= width * .45:
                self.stroke_distance += distance
                self.stroke_until = now + 1
                if self.stroke_distance >= width * .32:
                    self.stroke_distance = 0
                    self.pet_streak = self.pet_streak + 1 if now-self.last_pet < 25 else 1
                    self.last_pet = now
                    return self.reaction('meme_smug' if self.pet_streak >= 2 else 'pat', now, 8)
        else:
            self.stroke_distance = 0
        if self.near_since is not None and now - self.near_since >= 4 and not moving:
            reaction = self.reaction('meme_shock' if now-self.near_since >= 12 else 'curious', now, 45)
            if reaction:return reaction
        if moving:
            return None
        if now >= self.next_stretch:
            self.next_stretch = now + self.random.uniform(180, 300)
            return 'stretch'
        if now >= self.next_sit:
            self.next_sit = now + self.random.uniform(240, 420)
            return 'sit'
        if now >= self.next_focus and idle < 3 and now - self.active_since >= 45 and not near:
            self.next_focus = now + self.random.uniform(120, 210)
            return 'attentive'
        if now >= self.next_micro:
            self.next_micro = now + self.random.uniform(*( (55, 100) if quiet else (28, 55)))
            options = ['look_around', 'blink_slow', 'double_blink', 'wing_adjust', 'tail_flick']
            if mood > -.25:options.extend(['content', 'bashful_smile'])
            if 15 <= idle < 90:options.extend(['daydream', 'head_tilt'])
            if 40 <= idle < 90:options.append('meme_flop')
            if mood > .5:options.append('meme_smug')
            if near:options.extend(['head_tilt', 'attentive'])
            options = [name for name in options if name not in self.recent] or ['blink_slow']
            self.last_micro = self.random.choice(options)
            return self.last_micro
        return None


def expression_values(action, elapsed, duration, blink, dx, dy, reduced=False):
    """Expression clips return to neutral at their own duration, without new textures."""
    import math
    progress = min(1.0, max(0.0, elapsed / max(.1, duration)))
    ramp = min(1.0,progress/.18,(1-progress)/.18)
    pulse = max(0.0,ramp) ** 2 * (3-2*max(0.0,ramp))
    values = {}
    if action in ('notice', 'curious', 'look_around', 'edge_peek', 'head_tilt', 'attentive'):
        gaze = math.sin(elapsed * 2) * .9 if action in ('look_around', 'edge_peek') else dx * .9
        values.update(ParamEyeBallX=gaze, ParamBrowLY=.2*pulse, ParamBrowRY=.2*pulse)
        if action == 'head_tilt':values.update(ParamEyeBallY=.45*pulse, ParamBrowRY=.6*pulse)
        if action == 'attentive':values.update(ParamEyeLOpen=blink*(1-.15*pulse), ParamEyeROpen=blink*(1-.15*pulse))
    elif action in ('pat', 'content', 'relieved', 'settle', 'bashful_smile'):
        opening = blink * (1 - (.96 if action in ('pat', 'content') else .72) * pulse)
        values.update(ParamEyeLOpen=opening, ParamEyeROpen=opening,
                      ParamMouthForm=.6*pulse, ParamCheek=.4*pulse)
        if action == 'bashful_smile':
            values.update(ParamEyeLOpen=blink*(1-.98*pulse),ParamEyeROpen=blink,
                          ParamEyeBallY=-.45*pulse,ParamEyeBallX=-.45*pulse)
    elif action in ('blink_slow', 'double_blink'):
        centers = (.32, .59) if action == 'double_blink' else (.45,)
        half_width = .12 if action == 'double_blink' else .35
        closed = max(min(1,max(0, 1-abs(progress-center)/half_width)*1.6) for center in centers)
        values.update(ParamEyeLOpen=blink*(1-closed), ParamEyeROpen=blink*(1-closed))
    elif action in ('drowsy', 'yawn', 'daydream', 'sleepy_nod'):
        depth = .98 if action == 'sleepy_nod' else .9 if action in ('drowsy', 'yawn') else .65
        values.update(ParamEyeLOpen=blink*(1-depth*pulse), ParamEyeROpen=blink*(1-depth*pulse),
                      ParamEyeBallY=-.3*pulse, ParamMouthOpenY=.25*pulse if action == 'yawn' else 0)
        if action == 'daydream':values['ParamEyeBallX']=.75*pulse
    elif action in ('wake_up', 'perk_up'):
        opening = min(1, elapsed/.8) if action == 'wake_up' else 1
        values.update(ParamEyeLOpen=blink*opening, ParamEyeROpen=blink*opening,
                      ParamMouthForm=.6*pulse, ParamBrowLY=.15*pulse, ParamBrowRY=.15*pulse)
    elif action in ('drag', 'fall', 'startled'):
        strength = pulse if action == 'startled' else 1
        values.update(ParamEyeLOpen=1, ParamEyeROpen=1, ParamBrowLY=.35*strength,
                      ParamBrowRY=.35*strength, ParamMouthOpenY=.15*strength)
    elif action in ('shy', 'glance_away'):
        values.update(ParamEyeLOpen=blink*(1-.35*pulse), ParamEyeROpen=blink*(1-.35*pulse),
                      ParamEyeBallY=-.3*pulse, ParamEyeBallX=dx*.7*(1-pulse), ParamMouthForm=.5*pulse)
    if not reduced:
        if action == 'wing_adjust':
            values.update(ParamWingL=16*pulse, ParamWingR=-12*pulse,
                          ParamEyeBallY=-.2*pulse)
        elif action == 'tail_flick':
            values.update(ParamTail=18*math.sin(progress*math.pi*3)*pulse,
                          ParamEyeBallX=-.4*pulse)
    return values


def reaction_pose(action, elapsed, reduced=False, duration=2.4):
    """Whole-character motion keeps the conservative rig's cut edges together."""
    if reduced:
        return 0.0, 0.0, 1.0, 1.0
    import math
    envelope = math.sin(math.pi * min(1.0, max(0.0, elapsed / max(.1, duration))))
    if action == 'meme_shock':
        return -4*envelope, -5*envelope, 1.0, 1.0
    if action == 'meme_smug':
        return math.sin(elapsed*7)*2*envelope, -5*abs(math.sin(elapsed*5))*envelope, 1.0, 1.0
    if action == 'meme_pout':
        return math.sin(elapsed*10)*2*envelope, -2*abs(math.sin(elapsed*8))*envelope, 1.0, 1.0
    if action == 'meme_tears':
        return math.sin(elapsed*14)*.8*envelope, 0.0, 1.0, 1.0
    if action == 'meme_dizzy':
        return math.sin(elapsed*5)*4*envelope, 0.0, 1.0, 1.0
    if action in ('notice', 'curious', 'look_around', 'edge_peek', 'tail_flick', 'wing_adjust', 'shy', 'head_tilt', 'glance_away', 'daydream', 'bashful_smile'):
        angle = 4.0 if action=='head_tilt' else -3.0 if action=='glance_away' else 2.8
        return angle * envelope, 0.0, 1.0, 1.0
    if action in ('happy', 'content', 'pat', 'wake_up', 'perk_up'):
        return math.sin(elapsed * 3) * 2.2 * envelope, -4 * envelope, 1.0, 1.0
    if action == 'stretch':
        return 0.0, -1.5 * envelope, 1 - .009 * envelope, 1 + .012 * envelope
    if action in ('drowsy', 'yawn'):
        return -1.2 * envelope, 0.0, 1.0, 1.0
    if action == 'sleepy_nod':
        return 0.0, 1.8 * envelope, 1.0, 1.0
    if action in ('settle', 'relieved'):
        return 0.0, 1.2 * envelope, 1 + .004 * envelope, 1 - .004 * envelope
    return 0.0, 0.0, 1.0, 1.0
