# Harmonica Macro Toolkit

把 **MIDI** 或 **罗技 G HUB 的 Lua 脚本**转换成 **雷蛇雷云 4（Razer Synapse 4）宏文件**，用于在游戏里吹口琴。

网页版双击即可使用，不需要安装任何环境，文件全程在本地处理，不会上传。

---

## 键位映射

游戏内口琴的默认键位：

| 操作 | 音 | MIDI 编号 |
|---|---|---|
| `z x c v b n m` | C D E F G A B（中央 C 八度） | 60–71 |
| 按住**右键** + 键 | 高八度 | 72–83 |
| 按住**左键** + 键 | 低八度 | 48–59 |
| 按住**中键** + 键 | 升半音（黑键 = 下方白键 + 中键） | — |
| `,`（可选） | 高音 C5，不用按右键 | 72 |

超出 48–83 的音会自动折叠回可演奏范围，工具会提示折叠了多少个。

---

## 工具一览

| 文件 | 说明 | 依赖 |
|---|---|---|
| `midi2razer.html` | **MIDI → 雷云 4 宏** | 无，浏览器打开 |
| `lua2razer.html` | **罗技 Lua → 雷云 4 宏** | 无，浏览器打开 |
| `lua2razer.py` | lua转xml的命令行版本 | Python + `mido` |
| `midi2razer.py` | MIDI 转换的命令行版，可批量处理 | Python + `mido` |

网页版和 Python 版的转换逻辑完全一致，输出的事件逐条相同。网页版自带一个精简的 MIDI 解析器，所以不需要 `mido`；遇到冷门格式的 MIDI 打不开时，改用 mido库通常能解决（应该吧）。

### 快速开始

**网页版**：下载 `.html`，双击用浏览器打开，把文件拖进去，调参数、试听，然后下载 `.xml`。

**Python 版**：

```bash
pip install mido
python midi2razer.py song.mid             
python midi2razer.py song.mid --transpose -12 --speed 0.9
python midi2razer.py song.mid --split 40  # 长曲子拆段
python midi2razer.py song.mid --legato 0.8 --min-hold 40 --breath 20 --gap 10   # 快速曲子
```

**导入**：雷云 4 → 宏 → 宏列表旁的 `⋯` → 导入，选生成的 `.xml`，再绑定到侧键。

---

## 参数说明

| 参数 | 默认 | 作用 |
|---|---|---|
| `--speed` | 1.0 | 速度倍率，延迟除以它 |
| `--transpose` | 0 | 移调半音数，`-12` = 降一个八度 |
| `--legato` | 0.9 | 按住时长占音符时值的比例，越小越跳跃 |
| `--min-hold` | 60 | 最短按住毫秒数，太小游戏可能吹不出声 |
| `--breath` | 30 | 两个音之间至少松开的毫秒数，太小会连成一片 |
| `--gap` | 15 | 鼠标键提前按下的毫秒数，保证音符准点 |
| `--comma` | 关 | 高音 C5 改用逗号键，减少鼠标操作 |
| `--split` | 0 | 每 N 秒拆一个宏，0 为不拆 |

常见问题：

- 提示**「N 个音太密被推后」**：按键来不及，减小 `--min-hold` / `--breath`，或降低 `--speed`。
- 提示**「N 个音超出音域被折叠」**：用 `--transpose` 整体移调（图形界面有「自动移调」按钮）。
- 长曲子导入后雷云编辑器卡顿：用 `--split` 拆成几段，分别绑到不同按键。拆分只发生在所有键都松开的时刻，不会把音符切断。

---

## 雷云 4 宏文件格式

逆向自雷云 4 导出的宏文件，仅供参考
```xml
<Macro>
   <Name>宏名称</Name>
   <MacroEvents>
      <MacroEvent>                       <!-- 固定首条，编辑器使用 -->
         <Type>actionBar</Type>
         <recordProfile/>
         <selected>false</selected>
      </MacroEvent>

      <!-- Type 0：延迟，单位秒 -->
      <MacroEvent>
         <Type>0</Type>
         <Number>0.54</Number>
         <selected>false</selected>
      </MacroEvent>

      <!-- Type 1：键盘。Makecode 为 Windows 虚拟键码，State 0=按下 1=松开 -->
      <MacroEvent>
         <Type>1</Type>
         <Id>1789608945229</Id>
         <KeyEvent>
            <Makecode>90</Makecode>
            <State>0</State>
         </KeyEvent>
         <flag>0</flag>
         <selected>false</selected>
         <isPairing>false</isPairing>
      </MacroEvent>

      <!-- Type 2：鼠标。MouseButton 0=左 1=右 2=中 -->
      <MacroEvent>
         <Type>2</Type>
         <Id>1789608945230</Id>
         <MouseEvent>
            <MouseButton>2</MouseButton>
            <State>0</State>
         </MouseEvent>
         <flag>0</flag>
         <selected>false</selected>
         <isPairing>false</isPairing>
      </MacroEvent>
   </MacroEvents>
   <DelaySetting>0</DelaySetting>
   <Guid>随机 UUID</Guid>
   <Version>4</Version>
   <MouseMoveType>none</MouseMoveType>
</Macro>
```

规则要点：

- **延迟是独立的一条事件**，不挂在按键上。这是雷云 4 与雷云 3 最大的区别，两代宏文件互不兼容。
- 相邻两条事件之间没有延迟行 = 0 延迟连续执行。
- **同一个键的按下与松开必须共用一个 `Id`**，全文件唯一即可。
- **松开事件在 `KeyEvent` 内多一个 `<flag>1</flag>`**，鼠标事件没有这一层。
- 外层 `<flag>` 与 `State` 相同：按下 0，松开 1。
- `selected` 与 `isPairing` 一律 `false`，对应编辑器里的勾选状态。
- 「按住右键 + Z」的写法：右键按下 → Z 按下 → Z 松开 → 右键松开，鼠标键包住音符键。

这里只测试了有关于吹口琴的部分，别的鼠标宏内容不明确

---

## 罗技 Lua 转换器

支持 G HUB 脚本中的线性按键序列：

- `PressKey` / `ReleaseKey` / `PressAndReleaseKey`
- `PressMouseButton` / `ReleaseMouseButton` / `PressAndReleaseMouseButton`（G HUB 编号 1 左 2 中 3 右，自动换算为雷云编号）
- `Sleep`
- 固定次数的 `for i = 1, N` 循环，自动展开
- `if event == "..._PRESSED"` 触发条件，自动识别并按「按下时播放」处理
- `if aborted() then return end` 一类的中止检查，自动忽略

**无法转换**（页面会列出具体行号）：条件判断、`while` / `repeat` 等次数不定的循环、鼠标移动与滚轮、随机数与变量计算。原脚本的触发键、Caps Lock 中止等逻辑不会带过来，需要在雷云里自行绑定。

---

## 提示

- 宏和脚本都是软件发出的输入，能否使用取决于游戏的用户协议，不保证不会被反作弊判定。请自行确认所玩游戏是否允许演奏类宏。
- 工具只做格式转换，不附带任何乐曲数据。请勿用本工具分发受版权保护的曲目，自制或公有领域的曲子（如古典乐）不受此限。

## License

MIT
