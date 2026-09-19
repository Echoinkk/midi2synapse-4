"""

  python midi2razer.py song.mid                 # 默认参数
  python midi2razer.py song.mid --speed 0.8     # 放慢到 80%
  python midi2razer.py song.mid --track 1       # 只用第1轨
  python midi2razer.py song.mid --split 60      # 每60秒拆成一个宏
  python midi2razer.py song.mid --transpose -12 # 整体降一个八度
  python midi2razer.py song.mid --legato 0.95   # 更连贯(0.7 更跳跃)
映射: z x c v b n m = C D E F G A B (中央C八度)
      按住右键 = 高八度, 按住左键 = 低八度, 按住中键 = 升半音
"""
import argparse, os, time, uuid
import xml.etree.ElementTree as ET
import mido

BASE = 60
WHITE = {0: 'Z', 2: 'X', 4: 'C', 5: 'V', 7: 'B', 9: 'N', 11: 'M'}
SHARP = {1: 0, 3: 2, 6: 5, 8: 7, 10: 9}
MOUSE = {'left': 0, 'right': 1, 'middle': 2}   # right=1 为推测, 请验证
USE_COMMA = False   # True: 高音C5 用逗号键吹

def note_to_action(note):
    off = note - BASE
    while off < -12: off += 12
    while off >= 24: off -= 12
    pc = off % 12
    sharp = pc in SHARP
    key, octave = WHITE[SHARP[pc] if sharp else pc], off // 12
    if USE_COMMA and not sharp and pc == 0 and octave == 1:
        key, octave = ',', 0
    return key, octave, sharp

def read_notes(path, track=None, speed=1.0, transpose=0):
    mid = mido.MidiFile(path)
    src = mid if track is None else mido.MidiFile(type=0, ticks_per_beat=mid.ticks_per_beat,
                                                   tracks=[mido.merge_tracks([mid.tracks[0], mid.tracks[track]])])
    t, notes, open_ = 0.0, [], {}
    for msg in src:
        t += msg.time
        ms = t / speed * 1000
        if msg.type == 'note_on' and msg.velocity > 0:
            if notes and abs(ms - notes[-1][0]) < 1:      # 和弦只保留最高音(口琴一次一个音)
                if msg.note + transpose <= notes[-1][1]: continue
                notes.pop()
            notes.append([ms, msg.note + transpose, None])
            open_[msg.note] = notes[-1]
        elif msg.type in ('note_off', 'note_on') and msg.note in open_:
            n = open_.pop(msg.note)
            if n[2] is None: n[2] = ms - n[0]
    for i, n in enumerate(notes):                          # 下一个音开始时强制结束
        nxt = notes[i + 1][0] if i + 1 < len(notes) else None
        if n[2] is None: n[2] = (nxt - n[0]) if nxt else 500
        if nxt is not None: n[2] = min(n[2], nxt - n[0])
    return [tuple(n) for n in notes]

def build_steps(notes, legato, min_hold, breath, gap_ms):
    """[(kind, name, state, at_ms)] kind: key/mouse, state: 0按下 1松开
    每个音按住 = 音长*legato, 且与下一个音之间至少留 breath ms 换气"""
    steps, cursor, squeezed = [], 0.0, 0
    for i, (at, note, dur) in enumerate(notes):
        key, octave, sharp = note_to_action(note)
        mods = (['right'] if octave == 1 else ['left'] if octave == -1 else []) + (['middle'] if sharp else [])
        start = at if not mods else at - gap_ms            # 修饰键提前按, 音符准点
        if start < cursor: squeezed += 1; start = cursor
        t = start
        for m in mods: steps.append(('mouse', m, 0, t))
        if mods: t += gap_ms
        nxt = notes[i + 1][0] if i + 1 < len(notes) else None
        end = at + dur * legato
        if nxt is not None:
            nxt_mod_gap = gap_ms if any(note_to_action(notes[i+1][1])[1:]) else 0
            end = min(end, nxt - breath - nxt_mod_gap)
        end = max(end, t + min_hold)
        steps.append(('key', key, 0, t))
        steps.append(('key', key, 1, end))
        for m in reversed(mods): steps.append(('mouse', m, 1, end))
        cursor = end + 1
    return steps, squeezed

def sub(parent, tag, text=None):
    e = ET.SubElement(parent, tag)
    if text is not None: e.text = str(text)
    return e

def write_xml(steps, name, out):
    root = ET.Element('Macro'); sub(root, 'Name', name)
    evs = sub(root, 'MacroEvents')
    bar = sub(evs, 'MacroEvent'); sub(bar, 'Type', 'actionBar'); sub(bar, 'recordProfile'); sub(bar, 'selected', 'false')
    base_id = int(time.time() * 1000); ids = {}; counter = 0; now = steps[0][3] if steps else 0
    for kind, nm, state, at in steps:
        d = round(at - now)
        if d > 0:
            e = sub(evs, 'MacroEvent'); sub(e, 'Type', 0)
            sub(e, 'Number', f'{d/1000:.3f}'.rstrip('0').rstrip('.')); sub(e, 'selected', 'false')
            now = at
        if state == 0:
            ids[(kind, nm)] = base_id + counter; counter += 1
        eid = ids[(kind, nm)]
        e = sub(evs, 'MacroEvent')
        if kind == 'key':
            sub(e, 'Type', 1); sub(e, 'Id', eid)
            k = sub(e, 'KeyEvent'); sub(k, 'Makecode', 188 if nm == ',' else ord(nm)); sub(k, 'State', state)
            if state == 1: sub(k, 'flag', 1)
        else:
            sub(e, 'Type', 2); sub(e, 'Id', eid)
            m = sub(e, 'MouseEvent'); sub(m, 'MouseButton', MOUSE[nm]); sub(m, 'State', state)
        sub(e, 'flag', state); sub(e, 'selected', 'false'); sub(e, 'isPairing', 'false')
    sub(root, 'DelaySetting', 0); sub(root, 'Guid', uuid.uuid4()); sub(root, 'Version', 4)
    sub(root, 'MouseMoveType', 'none')
    ET.indent(root, space='   ')
    ET.ElementTree(root).write(out, encoding='utf-8')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('midi'); ap.add_argument('--speed', type=float, default=1.0)
    ap.add_argument('--track', type=int); ap.add_argument('--transpose', type=int, default=0)
    ap.add_argument('--legato', type=float, default=0.9, help='按住时长占音长的比例')
    ap.add_argument('--min-hold', type=float, default=60, help='最短按住ms')
    ap.add_argument('--breath', type=float, default=30, help='两个音之间至少松开ms')
    ap.add_argument('--gap', type=float, default=15, help='修饰键按下到音符键的间隔ms')
    ap.add_argument('--comma', action='store_true', help='高音C5 用逗号键, 不按右键')
    ap.add_argument('--split', type=float, default=0, help='每N秒拆一个宏, 0=不拆')
    a = ap.parse_args()
    global USE_COMMA
    USE_COMMA = a.comma

    if a.track is None:
        for i, tr in enumerate(mido.MidiFile(a.midi).tracks):
            n = sum(1 for m in tr if m.type == 'note_on' and m.velocity > 0)
            if n: print(f'  轨道 {i}: {tr.name or "(无名)"}  {n} 个音')

    notes = read_notes(a.midi, a.track, a.speed, a.transpose)
    rng = [n for _, n, _ in notes]
    if rng:
        print(f'音域 MIDI {min(rng)}–{max(rng)}; 可直接演奏 48–83, 超出的会折叠八度')
    stem = os.path.splitext(os.path.basename(a.midi))[0]
    chunks = [notes]
    if a.split > 0 and notes:
        chunks, cur, start = [], [], notes[0][0]
        for n in notes:
            if n[0] - start >= a.split * 1000 and cur:
                chunks.append(cur); cur, start = [], n[0]
            cur.append(n)
        chunks.append(cur)
    for i, ch in enumerate(chunks, 1):
        steps, sq = build_steps(ch, a.legato, a.min_hold, a.breath, a.gap)
        name = stem if len(chunks) == 1 else f'{stem}_{i}'
        write_xml(steps, name, name + '.xml')
        print(f'{name}.xml: {len(ch)} 个音, {len(steps)} 个事件' + (f', {sq} 个音因太密被推后' if sq else ''))

if __name__ == '__main__':
    main()
