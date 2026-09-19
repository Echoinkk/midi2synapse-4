
"""
罗技 G HUB 的 Lua 脚本 -> 雷云4 (Razer Synapse 4) 宏 XML

    python lua2razer.py script.lua
    python lua2razer.py script.lua --entry play --speed 0.9 --split 40
    python lua2razer.py script.lua --list          # 只列出可用的入口函数

能转: PressKey / ReleaseKey / PressAndReleaseKey / Press(AndRelease)MouseButton / Sleep,
      固定次数的 for 循环, if event == "..._PRESSED" 触发条件, if aborted() then return end
不能转: 条件判断, while/repeat 循环, 鼠标移动与滚轮, 随机数与变量计算 (会提示行号)
"""
import argparse, os, re, sys, time, uuid
import xml.etree.ElementTree as ET

KW = set('and break do else elseif end false for function goto if in local nil not or repeat return then true until while'.split())
BINOP = set(['+', '-', '*', '/', '//', '%', '^', '..', '==', '~=', '<', '>', '<=', '>=', 'and', 'or', '=', ',',
             '&', '|', '~', '<<', '>>'])
NUM_RE = re.compile(r'0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+')
NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
OP_RE = re.compile(r'\.\.\.|\.\.|==|~=|<=|>=|<<|>>|//|::|.')


def lex(src):
    toks, i, line, n = [], 0, 1, len(src)

    def long_end(j):
        m = re.match(r'\[(=*)\[', src[j:])
        if not m:
            return -1
        close = ']' + m.group(1) + ']'
        k = src.find(close, j + len(m.group(0)))
        return n if k < 0 else k + len(close)

    while i < n:
        c = src[i]
        if c == '\n':
            line += 1; i += 1; continue
        if c.isspace():
            i += 1; continue
        if src.startswith('--', i):
            e = long_end(i + 2)
            j = e if e >= 0 else (src.find('\n', i) if src.find('\n', i) >= 0 else n)
            line += src.count('\n', i, j); i = j; continue
        if c == '[' and re.match(r'\[=*\[', src[i:]):
            e = long_end(i); raw = src[i:e]
            toks.append(('str', re.sub(r'^\[=*\[\n?|\]=*\]$', '', raw), line))
            line += raw.count('\n'); i = e; continue
        if c in '"\'':
            j, s = i + 1, []
            while j < n and src[j] != c:
                if src[j] == '\\':
                    s.append({'n': '\n', 't': '\t'}.get(src[j + 1], src[j + 1])); j += 2
                else:
                    if src[j] == '\n':
                        line += 1
                    s.append(src[j]); j += 1
            toks.append(('str', ''.join(s), line)); i = j + 1; continue
        m = NUM_RE.match(src, i)
        if m:
            v = m.group(0)
            toks.append(('num', int(v, 16) if v[:2].lower() == '0x' else float(v), line)); i = m.end(); continue
        m = NAME_RE.match(src, i)
        if m:
            toks.append(('name', m.group(0), line)); i = m.end(); continue
        m = OP_RE.match(src, i)
        toks.append(('op', m.group(0), line)); i = m.end()
    toks.append(('eof', '', line))
    return toks


#  结构解析
class Parser:
    def __init__(self, toks):
        self.T, self.p = toks, 0

    def pk(self, o=0):
        return self.T[min(self.p + o, len(self.T) - 1)]

    def nx(self):
        t = self.T[self.p]; self.p += 1; return t

    def is_(self, v, o=0):
        t = self.pk(o); return t[0] != 'str' and t[1] == v

    def expect(self, v):
        if not self.is_(v):
            raise SyntaxError(f'第 {self.pk()[2]} 行附近无法解析（在期望 {v}，遇到 {self.pk()[1] or "文件结尾"}）')
        return self.nx()

    def skip_balanced(self):
        op = self.nx()[1]; close = {'(': ')', '[': ']', '{': '}'}[op]; d = 1
        while d and self.pk()[0] != 'eof':
            t = self.nx()
            if t[0] == 'op':
                if t[1] == op: d += 1
                elif t[1] == close: d -= 1
            elif t[0] == 'name' and t[1] == 'function':
                self.skip_func_body()

    def skip_func_body(self):
        while not self.is_('('):
            self.nx()
        self.skip_balanced(); self.block(['end']); self.expect('end')

    def skip_expr(self):
        ended = False
        while self.pk()[0] != 'eof':
            k, v, _ = self.pk()
            if ended:
                if k == 'str' or (k == 'op' and v in '([{.:'):
                    ended = False
                elif (k in ('op', 'name')) and v in BINOP:
                    self.nx(); ended = False; continue
                else:
                    break
            if k == 'op' and v in '([{':
                self.skip_balanced(); ended = True; continue
            if k == 'name' and v == 'function':
                self.nx(); self.skip_func_body(); ended = True; continue
            if (k == 'name' and v == 'not') or (k == 'op' and v in ('-', '#', '~', '.', ':')):
                self.nx(); continue
            if k == 'name' and v in KW and v not in ('true', 'false', 'nil'):
                break
            if k == 'op' and v != '...':
                break
            self.nx(); ended = True

    def args(self, s, e):
        out, cur, d = [], [], 0
        for t in self.T[s:e]:
            if t[0] == 'op' and t[1] in '([{': d += 1
            if t[0] == 'op' and t[1] in ')]}': d -= 1
            if d == 0 and t[0] == 'op' and t[1] == ',':
                out.append(cur); cur = []
            else:
                cur.append(t)
        if cur:
            out.append(cur)
        res = []
        for a in out:
            if len(a) == 1 and a[0][0] in ('str', 'num'):
                res.append({'lit': a[0][1]})
            elif len(a) == 2 and a[0][1] == '-' and a[1][0] == 'num':
                res.append({'lit': -a[1][1]})
            else:
                res.append({'raw': ' '.join(str(x[1]) for x in a)})
        return res

    def block(self, terms):
        out = []
        while self.pk()[0] != 'eof' and not (self.pk()[0] == 'name' and self.pk()[1] in terms):
            k, v, line = self.pk()
            if k == 'op' and v == ';':
                self.nx(); continue
            if k == 'op' and v == '::':
                self.nx(); self.nx(); self.nx(); continue
            if k == 'name':
                if (v == 'local' and self.is_('function', 1)) or v == 'function':
                    if v == 'local': self.nx()
                    self.nx(); name = ''
                    while not self.is_('('):
                        name += str(self.nx()[1])
                    self.skip_balanced(); body = self.block(['end']); self.expect('end')
                    out.append({'type': 'funcdef', 'name': name, 'body': body, 'line': line}); continue
                if v == 'local':
                    self.nx(); self.skip_expr(); continue
                if v == 'if':
                    self.nx(); s = self.p; self.skip_expr()
                    cond = ' '.join(str(t[1]) for t in self.T[s:self.p]); self.expect('then')
                    branches = [{'cond': cond, 'body': self.block(['elseif', 'else', 'end'])}]
                    while self.is_('elseif'):
                        self.nx(); s = self.p; self.skip_expr()
                        cond = ' '.join(str(t[1]) for t in self.T[s:self.p]); self.expect('then')
                        branches.append({'cond': cond, 'body': self.block(['elseif', 'else', 'end'])})
                    if self.is_('else'):
                        self.nx(); branches.append({'cond': None, 'body': self.block(['end'])})
                    self.expect('end')
                    out.append({'type': 'if', 'branches': branches, 'line': line}); continue
                if v == 'for':
                    self.nx(); s = self.p
                    while not self.is_('do') and self.pk()[0] != 'eof':
                        self.nx()
                    num = None
                    if self.T[s + 1][1] == '=':
                        a = self.args(s + 2, self.p)
                        if len(a) >= 2 and all('lit' in x and isinstance(x['lit'], (int, float)) for x in a):
                            num = [x['lit'] for x in a]
                    self.expect('do'); body = self.block(['end']); self.expect('end')
                    out.append({'type': 'for', 'num': num, 'body': body, 'line': line}); continue
                if v in ('while', 'repeat'):
                    self.nx()
                    if v == 'while':
                        self.skip_expr(); self.expect('do'); body = self.block(['end']); self.expect('end')
                    else:
                        body = self.block(['until']); self.expect('until'); self.skip_expr()
                    out.append({'type': 'loop', 'kind': v, 'body': body, 'line': line}); continue
                if v == 'do':
                    self.nx(); body = self.block(['end']); self.expect('end')
                    out.append({'type': 'do', 'body': body, 'line': line}); continue
                if v == 'return':
                    self.nx()
                    if not (self.pk()[0] == 'name' and self.pk()[1] in ('end', 'else', 'elseif', 'until')) \
                            and self.pk()[0] != 'eof':
                        self.skip_expr()
                    out.append({'type': 'return', 'line': line}); continue
                if v in ('break', 'goto'):
                    self.nx()
                    if v == 'goto': self.nx()
                    out.append({'type': 'other', 'line': line}); continue
                if v not in KW and self.is_('(', 1):
                    self.nx(); s = self.p + 1; self.skip_balanced(); a = self.args(s, self.p - 1)
                    if (self.pk()[0] == 'op' and self.pk()[1] in ('(', '[', '.', ':', '=')) or self.pk()[0] == 'str':
                        self.skip_expr(); out.append({'type': 'other', 'line': line}); continue
                    out.append({'type': 'call', 'name': v, 'args': a, 'line': line}); continue
            before = self.p; self.skip_expr()
            if self.p == before:
                self.nx()
            out.append({'type': 'other', 'line': line})
        return out


# =按键映射=
VK = {'escape': 27, 'tab': 9, 'capslock': 20, 'lshift': 160, 'rshift': 161, 'lctrl': 162, 'rctrl': 163,
      'lalt': 164, 'ralt': 165, 'lgui': 91, 'rgui': 92, 'spacebar': 32, 'space': 32, 'enter': 13,
      'backspace': 8, 'minus': 189, 'equal': 187, 'lbracket': 219, 'rbracket': 221, 'backslash': 220,
      'semicolon': 186, 'quote': 222, 'tilde': 192, 'comma': 188, 'period': 190, 'slash': 191,
      'up': 38, 'down': 40, 'left': 37, 'right': 39, 'home': 36, 'end': 35, 'pageup': 33, 'pagedown': 34,
      'insert': 45, 'delete': 46, 'numlock': 144}
VK.update({f'f{i}': 111 + i for i in range(1, 25)})
VK.update({f'num{i}': 96 + i for i in range(10)})
# G HUB是: 1左 2中 3右   ->   雷云: 0左 1右 2中
MOUSE_MAP = {1: (0, '左键'), 2: (2, '中键'), 3: (1, '右键')}
PRESS = {'PressKey', 'PressAndReleaseKey', 'PressMouseButton', 'PressAndReleaseMouseButton',
         'MoveMouseRelative', 'MoveMouseTo', 'MoveMouseWheel', 'MoveMouseToVirtual'}


def key_code(name):
    k = str(name).lower()
    if len(k) == 1 and k.isalpha():
        return ord(k.upper()), k.upper(), True
    if len(k) == 1 and k.isdigit():
        return ord(k), k, False
    if k in VK:
        return VK[k], k, False
    return None


#执行
class Runner:
    def __init__(self, ast, speed=1.0):
        self.ast, self.speed = ast, speed
        self.funcs = {}
        self._collect(ast)
        self.events, self.warn, self.used_keys, self.used_mouse, self.triggers = [], [], {}, {}, []
        self.t, self.held, self.skipped_checks = 0.0, {}, 0

    def _collect(self, lst):
        for s in lst:
            if s['type'] == 'funcdef':
                self.funcs[s['name']] = s; self._collect(s['body'])
            elif 'body' in s:
                self._collect(s['body'])
            elif 'branches' in s:
                for b in s['branches']:
                    self._collect(b['body'])

    def acts(self, lst, seen=None):
        seen = seen or set(); c = 0
        for s in lst:
            if s['type'] == 'call':
                if s['name'] in PRESS:
                    c += 1
                elif s['name'] in self.funcs and s['name'] not in seen:
                    seen.add(s['name']); c += self.acts(self.funcs[s['name']]['body'], seen); seen.discard(s['name'])
            elif s['type'] == 'for' and s['num']:
                a, b = s['num'][0], s['num'][1]; st = s['num'][2] if len(s['num']) > 2 else 1
                c += self.acts(s['body'], seen) * max(0, int((b - a) / st) + 1)
            elif s['type'] != 'funcdef' and 'body' in s:
                c += self.acts(s['body'], seen)
            elif 'branches' in s:
                for br in s['branches']:
                    c += self.acts(br['body'], seen)
        return c

    def entries(self):
        out = [(n, f['line'], self.acts(f['body'], {n})) for n, f in self.funcs.items()]
        out = [e for e in out if e[2] > 0]
        top = self.acts([s for s in self.ast if s['type'] != 'funcdef'])
        if top:
            out.append(('(文件顶层)', 1, top))
        return sorted(out, key=lambda e: -e[2])

    def W(self, line, msg):
        for w in self.warn:
            if w[0] == line and w[1] == msg:
                w[2] += 1; return
        self.warn.append([line, msg, 1])

    def press(self, kind, code):
        if (kind, code) in self.held: return
        self.held[(kind, code)] = True
        self.events.append((kind, code, 0, self.t))

    def release(self, kind, code):
        if (kind, code) not in self.held: return
        del self.held[(kind, code)]
        self.events.append((kind, code, 1, self.t))

    def key_args(self, s):
        out = []
        for a in s['args']:
            if 'lit' not in a:
                self.W(s['line'], f"{s['name']} 的参数不是常量（{a['raw']}），已跳过"); continue
            if isinstance(a['lit'], (int, float)):
                self.W(s['line'], f"{s['name']} 使用扫描码 {a['lit']}，暂不支持，已跳过"); continue
            kc = key_code(a['lit'])
            if not kc:
                self.W(s['line'], f'未知按键名 "{a["lit"]}"，已跳过'); continue
            self.used_keys[a['lit']] = kc; out.append(kc[0])
        return out

    def mouse_arg(self, s):
        a = s['args'][0] if s['args'] else None
        if not a or 'lit' not in a:
            self.W(s['line'], f"{s['name']} 的参数不是常量，已跳过"); return None
        m = MOUSE_MAP.get(int(a['lit']))
        if not m:
            self.W(s['line'], f"鼠标键 {int(a['lit'])}（侧键等）在雷云宏里的编号未知，已跳过"); return None
        self.used_mouse[int(a['lit'])] = m; return m[0]

    def exec(self, lst, depth=0):
        for s in lst:
            ty = s['type']
            if ty == 'call':
                n = s['name']
                if n == 'Sleep':
                    a = s['args'][0] if s['args'] else None
                    if a and isinstance(a.get('lit'), (int, float)):
                        self.t += max(0.0, float(a['lit'])) / self.speed
                    else:
                        self.W(s['line'], 'Sleep 的参数不是常量，已忽略该延迟')
                elif n == 'PressKey':
                    for c in self.key_args(s): self.press('key', c)
                elif n == 'ReleaseKey':
                    for c in self.key_args(s): self.release('key', c)
                elif n == 'PressAndReleaseKey':
                    cs = self.key_args(s)
                    for c in cs: self.press('key', c)
                    for c in cs: self.release('key', c)
                elif n == 'PressMouseButton':
                    c = self.mouse_arg(s)
                    if c is not None: self.press('mouse', c)
                elif n == 'ReleaseMouseButton':
                    c = self.mouse_arg(s)
                    if c is not None: self.release('mouse', c)
                elif n == 'PressAndReleaseMouseButton':
                    c = self.mouse_arg(s)
                    if c is not None: self.press('mouse', c); self.release('mouse', c)
                elif n.startswith('MoveMouse'):
                    self.W(s['line'], f'{n}（鼠标移动/滚轮）暂不支持，已跳过')
                elif n in self.funcs and depth < 20 and self.acts(self.funcs[n]['body'], {n}) > 0:
                    if self.exec(self.funcs[n]['body'], depth + 1) == 'return':
                        continue
            elif ty == 'if':
                b0 = s['branches'][0]
                if len(s['branches']) == 1 and b0['body'] and any(x['type'] == 'return' for x in b0['body']) \
                        and all(x['type'] == 'return' or (x['type'] == 'call' and x['name'] not in PRESS)
                                for x in b0['body']):
                    self.skipped_checks += 1; continue
                if self.acts([s]) == 0:
                    continue
                trig = next((b for b in s['branches'] if b['cond'] and re.search(r'\b(event|arg)\b', b['cond'])
                             and 'PRESSED' in b['cond'] and self.acts(b['body']) > 0), None)
                if trig:
                    self.triggers.append((s['line'], trig['cond']))
                    if any(b is not trig and self.acts(b['body']) > 0 for b in s['branches']):
                        self.W(s['line'], '松开触发（RELEASED）或其它分支里的动作无法放进同一个宏，已跳过')
                    if self.exec(trig['body'], depth) == 'return':
                        return 'return'
                else:
                    self.W(s['line'], f"条件分支（if {b0['cond']}）无法在宏里判断，其中的按键动作已跳过")
            elif ty == 'for':
                if self.acts(s['body']) == 0:
                    continue
                if not s['num']:
                    self.W(s['line'], '非数字计数的 for 循环无法展开，已跳过'); continue
                a, b = s['num'][0], s['num'][1]; st = s['num'][2] if len(s['num']) > 2 else 1
                cnt, v = 0, a
                while (v <= b) if st > 0 else (v >= b):
                    cnt += 1
                    if cnt > 10000:
                        self.W(s['line'], '循环次数过多，已截断'); break
                    if self.exec(s['body'], depth) == 'return':
                        return 'return'
                    v += st
            elif ty == 'loop':
                if self.acts(s['body']) > 0:
                    self.W(s['line'], f"{s['kind']} 循环次数不确定，已跳过（可在雷云里用“按住时重复”近似）")
            elif ty == 'do':
                if self.exec(s['body'], depth) == 'return':
                    return 'return'
            elif ty == 'return':
                return 'return'

    def run(self, entry):
        body = [s for s in self.ast if s['type'] != 'funcdef'] if entry == '(文件顶层)' else self.funcs[entry]['body']
        self.exec(body)
        left = list(self.held.keys())
        for kind, code in left:
            self.release(kind, code)
        if left:
            self.W(0, f'结尾有 {len(left)} 个键没松开，已自动补上松开')
        return self


# 输出
def _sub(p, tag, text=None):
    e = ET.SubElement(p, tag)
    if text is not None:
        e.text = str(text)
    return e


def write_xml(events, name, out_path):
    root = ET.Element('Macro'); _sub(root, 'Name', name)
    evs = _sub(root, 'MacroEvents')
    bar = _sub(evs, 'MacroEvent')
    _sub(bar, 'Type', 'actionBar'); _sub(bar, 'recordProfile'); _sub(bar, 'selected', 'false')
    base_id, counter, ids = int(time.time() * 1000), 0, {}
    now = events[0][3] if events else 0
    for kind, code, state, at in events:
        d = round(at - now)
        if d > 0:
            e = _sub(evs, 'MacroEvent'); _sub(e, 'Type', 0)
            _sub(e, 'Number', f'{d / 1000:.3f}'.rstrip('0').rstrip('.')); _sub(e, 'selected', 'false')
            now = at
        if state == 0:
            ids[(kind, code)] = base_id + counter; counter += 1
        e = _sub(evs, 'MacroEvent')
        if kind == 'key':
            _sub(e, 'Type', 1); _sub(e, 'Id', ids[(kind, code)])
            k = _sub(e, 'KeyEvent'); _sub(k, 'Makecode', code); _sub(k, 'State', state)
            if state == 1:
                _sub(k, 'flag', 1)
        else:
            _sub(e, 'Type', 2); _sub(e, 'Id', ids[(kind, code)])
            m = _sub(e, 'MouseEvent'); _sub(m, 'MouseButton', code); _sub(m, 'State', state)
        _sub(e, 'flag', state); _sub(e, 'selected', 'false'); _sub(e, 'isPairing', 'false')
    _sub(root, 'DelaySetting', 0); _sub(root, 'Guid', uuid.uuid4())
    _sub(root, 'Version', 4); _sub(root, 'MouseMoveType', 'none')
    ET.indent(root, space='   ')
    ET.ElementTree(root).write(out_path, encoding='utf-8')


def split_events(events, seconds):
    """只在所有键都松开的时刻进行切分"""
    if not seconds or not events:
        return [events]
    parts, cur, start, held = [], [], events[0][3], 0
    for e in events:
        if held == 0 and cur and e[2] == 0 and e[3] - start >= seconds * 1000:
            parts.append(cur); cur = []; start = e[3]
        cur.append(e); held += 1 if e[2] == 0 else -1
    if cur:
        parts.append(cur)
    return parts


def read_text(path):
    data = open(path, 'rb').read()
    for enc in ('utf-8', 'gbk', 'latin-1'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', 'replace')


def main():
    ap = argparse.ArgumentParser(description='罗技 Lua 转 雷云4 宏')
    ap.add_argument('lua')
    ap.add_argument('--entry', help='从哪个函数开始执行（默认按键动作最多的那个）')
    ap.add_argument('--list', action='store_true', help='只列出可用入口')
    ap.add_argument('--speed', type=float, default=1.0, help='速度倍率，延迟除以它')
    ap.add_argument('--split', type=float, default=0, help='每 N 秒拆一个宏，0 = 不拆')
    a = ap.parse_args()

    ast = Parser(lex(read_text(a.lua))).block([])
    entries = Runner(ast).entries()
    if not entries:
        sys.exit('没在脚本里找到 PressKey / PressMouseButton 之类的按键动作')
    print('可用入口：')
    for name, line, acts in entries:
        print(f'  {name}  (第 {line} 行, {acts} 个按下动作)')
    if a.list:
        return

    entry = a.entry or entries[0][0]
    r = Runner(ast, a.speed).run(entry)
    downs = [e for e in r.events if e[2] == 0]
    kd = sum(1 for e in downs if e[0] == 'key')
    print(f'\n入口 {entry}：{kd} 次按键、{len(downs) - kd} 次鼠标键，'
          f'共 {len(r.events)} 个事件，时长约 {r.t / 1000:.1f} 秒')
    if r.triggers:
        print(f'  已识别触发条件 {r.triggers[0][1]}，按“按下时播放”处理')
    if r.skipped_checks:
        print(f'  跳过了 {r.skipped_checks} 处中止检查（雷云宏不需要）')
    if r.used_keys:
        print('  按键：' + '，'.join(f'{k}→{c[0]}' + ('' if c[2] else '(待验证)')
                                    for k, c in r.used_keys.items()))
    if r.used_mouse:
        print('  鼠标：' + '，'.join(f'{n}({m[1]})→{m[0]}' for n, m in r.used_mouse.items()))
    for line, msg, cnt in r.warn:
        print(f'  ! {"第 %d 行：" % line if line else ""}{msg}' + (f'（×{cnt}）' if cnt > 1 else ''))

    stem = re.sub(r'[-_]?logitech$', '', os.path.splitext(os.path.basename(a.lua))[0], flags=re.I).rstrip('-_ ')
    parts = split_events(r.events, a.split)
    for i, ev in enumerate(parts, 1):
        name = stem if len(parts) == 1 else f'{stem}_{i}'
        write_xml(ev, name, name + '.xml')
        print(f'✓ {name}.xml  约 {(ev[-1][3] - ev[0][3]) / 1000:.1f} 秒')


if __name__ == '__main__':
    main()
