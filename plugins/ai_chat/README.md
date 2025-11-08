AI 对话插件 ai_chat

简介
- 基于 NoneBot2 的通用 AI 对话插件，支持多模态输入（文本/图片）、工具调用（Function Calling）与可选 MCP、会话与人格系统、TTS 语音回复、摘要记忆等能力。

特性概览
- 多模态输入：自动将文本与图片封装为 Chat Completions 的 content parts。
- 图片解析：识别群/私聊图片、URL、Markdown 图片、data:image URI，并按需压缩（最长边/质量）。
- 工具调用：
  - 装饰器注册自定义工具（OpenAI Function Calling JSON Schema）。
  - 可选接入 MCP（Model Context Protocol），以 mcp:<server>:<tool> 形式使用外部工具。
  - 支持多轮工具迭代，直到模型不再请求工具或达到上限。
- 会话系统：按会话（群/私）持久化历史与状态，支持清空/暂停/切换人格/服务商。
- 摘要记忆：可选按轮数阈值与间隔自动生成对话摘要并注入 System Prompt。
- TTS 输出：统一接口支持 openai/http/command 三种模式，自动将文本转换为音频文件。
- 短期群聊记忆：以“用户名/时间: 内容”记录近 N 行群聊上下文，提升主动回复质量。

安装与启用
- 依赖安装（UTF-8 环境）：
  - 使用项目根目录的 `requirements.txt` 安装：
    pip install -r requirements.txt
  - 鍏抽敭渚濊禆锛歰penai>=1.0, pydantic>=2, sqlalchemy>=2, sqlmodel, Pillow, httpx, aiosqlite銆?
- 鍚敤鎻掍欢锛氱‘淇濆湪 NoneBot 鍔犺浇 `nonebot_plugin_entertain` 鍚庯紝鑷姩鍔犺浇鏈彃浠讹紙ai_chat 鐨?`__init__.py` 涓凡 `require("nonebot_plugin_entertain")`锛夈€?
- 閰嶇疆鏂囦欢涓庣洰褰曪細
  - 涓婚厤缃細`config/ai_chat/config.json`
  - 浜烘牸鐩綍锛歚config/ai_chat/personas/`锛堟敮鎸?.md/.txt/.docx锛屼紭鍏?.md锛?
  - TTS 闊抽杈撳嚭锛歚data/ai_chat/tts/`
  - 鍙敤鐜鍙橀噺瑕嗙洊閰嶇疆鐩綍锛歚NPE_CONFIG_DIR=/your/config/dir`

蹇€熷紑濮?
1) 鍒涘缓鏈€灏忓彲鐢ㄩ厤缃?`config/ai_chat/config.json`锛?
```
{
  "api": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-xxxxxxxxxxxxxxxx",
      "model": "gpt-4o-mini",
      "timeout": 60
    }
  },
  "session": {
    "api_active": "openai",
    "default_temperature": 0.7,
    "max_rounds": 8,
    "chatroom_history_max_lines": 200,
    "active_reply_enable": false,
    "active_reply_probability": 0.1,
    "active_reply_prompt_suffix": "璇峰熀浜庢渶杩戞秷鎭嚜鐒跺湴鍥炲锛歿message}\n鍙緭鍑哄繀瑕佸唴瀹广€?
  }
}
```
2) 甯歌 `base_url` 绀轰緥锛堟寜鏈嶅姟鍟嗚嚜琛屾浛鎹級锛?
- OpenAI: `https://api.openai.com/v1`
- 绗笁鏂逛唬鐞?鑱氬悎锛堢ず渚嬶級锛歚https://one-api.your-domain/v1`銆乣https://api.deepseek.com/v1`銆乣https://open.bigmodel.cn/api/paas/v4` 绛夈€傝浠ヤ緵搴斿晢鏂囨。涓哄噯銆?
3) 杩愯鍚庡湪缇よ亰 @鏈哄櫒浜?鍙戞秷鎭紝鎴栫鑱婄洿鎺ュ彂娑堟伅娴嬭瘯銆?

鍛戒护閫熸煡
- 瀵硅瘽
  - 缇よ亰闇€ @鏈哄櫒浜?鎴栧懡涓富鍔ㄥ洖澶嶏紱绉佽亰鐩存帴鍙戦€佹枃鏈?鍥剧墖鍗冲彲銆?
- 浼氳瘽绠＄悊
  - `#娓呯┖浼氳瘽` 娓呯┖褰撳墠浼氳瘽鍘嗗彶
  - `#浼氳瘽淇℃伅` 鏌ョ湅褰撳墠浼氳瘽鐘舵€?
  - `#寮€鍚疉I` / `#鍏抽棴AI`锛堢鐞嗗憳锛夊垏鎹細璇濆惎鐢ㄧ姸鎬?
- 浜烘牸
  - `#浜烘牸鍒楄〃`锛堢鐞嗗憳锛夋煡鐪嬪彲鐢ㄤ汉鏍?
  - `#鍒囨崲浜烘牸 <key>`锛堢鐞嗗憳锛夊垏鎹㈠綋鍓嶄細璇濅汉鏍?
- 鏈嶅姟鍟?
  - `#鏈嶅姟鍟嗗垪琛╜锛堣秴绠★級鏌ョ湅閰嶇疆涓殑鏈嶅姟鍟?
  - `#鍒囨崲鏈嶅姟鍟?<name>`锛堣秴绠★級鍒囨崲 `session.api_active`
- 宸ュ叿涓?TTS
  - `#宸ュ叿鍒楄〃`锛堣秴绠★級鏌ョ湅宸ュ叿锛堝惈 MCP 鍔ㄦ€佸伐鍏凤級
  - `#寮€鍚伐鍏?<name>` / `#鍏抽棴宸ュ叿 <name>`锛堣秴绠★級
  - `#寮€鍚疶TS` / `#鍏抽棴TTS`锛堣秴绠★級
- 绯荤粺
  - `#閲嶈浇AI閰嶇疆`锛堣秴绠★級閲嶆柊鍔犺浇閰嶇疆涓庝汉鏍?

鍥剧墖杈撳叆璇存槑
- 鏀寔鏉ユ簮锛?
  - QQ 鍥剧墖娑堟伅锛堣嚜鍔ㄤ笅杞?鍘嬬缉鍚庤浆 data:image;base64锛?
  - 鐩存帴绮樿创 URL锛坔ttp/https锛夋垨 data:image;base64
  - 鏂囨湰涓殑 Markdown 鍥剧墖锛歚![alt](https://...)`
- 鍘嬬缉涓庤川閲忥細
  - `input.image_max_side` 鏈€闀胯竟鍍忕礌锛?0 鏃舵寜姣斾緥缂╂斁骞惰浆 JPEG锛?
  - `input.image_jpeg_quality` JPEG 璐ㄩ噺锛?-95锛夛紝榛樿 85

浜烘牸鏂囦欢锛坧ersonas锛?
- 浣嶇疆锛歚config/ai_chat/personas/`锛屾敮鎸?`.md/.txt/.docx`锛屼紭鍏?`.md`銆?
- `.md` 鏀寔鍙€?Front Matter锛?
```
---
name: 钀借惤澶ф柟
description: 鍙嬪杽銆佽€愬績銆佽〃杈炬竻鏅?
---

浣犳槸涓€浣嶅弸鍠勪笖琛ㄨ揪娓呮櫚鐨?AI 鍔╂墜锛屽洖绛旂畝娲併€佹潯鐞嗗垎鏄庛€?
```
- 鍒濇杩愯鐩綍涓虹┖鏃朵粎鍐欏叆绀轰緥浜烘牸锛歚默认人格.md`銆?
- 鍒囨崲浜烘牸锛歚#鍒囨崲浜烘牸 default`锛堢鐞嗗憳锛夈€?

宸ュ叿璋冪敤锛團unction Calling + MCP锛?
- 鍐呯疆宸ュ叿锛堝彲鍦ㄩ厤缃?`tools.builtin_tools` 涓惎鐢級锛?
  - `get_time` 褰撳墠鏃堕棿
  - `get_weather` 绠€鍗曠ず渚嬶紙鍙帴鍏ョ湡瀹?API锛?
- 鑷畾涔夊伐鍏锋敞鍐岀ず渚嬶紙`plugins/ai_chat/tools.py` 鐩稿悓椋庢牸锛夛細
```
from plugins.ai_chat.tools import register_tool

@register_tool(
    name="echo",
    description="鍥炴樉浼犲叆鏂囨湰",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"]
    }
)
async def tool_echo(text: str) -> str:
    return text
```
- MCP 鎺ュ叆锛?
  - 闇€瑕佸畨瑁?Python MCP SDK锛坄pip install modelcontextprotocol` 鎴栦緵搴斿晢 SDK锛夈€?
  - 鍦ㄩ厤缃腑寮€鍚細
```
{
  "tools": {
    "enabled": true,
    "max_iterations": 3,
    "builtin_tools": ["get_time", "mcp:*"],
    "mcp_enabled": true,
    "mcp_servers": [
      {
        "name": "calc",
        "command": "python",
        "args": ["-m", "your_calc_mcp_server"],
        "env": {"EXAMPLE": "1"}
      }
    ]
  }
}
```
  - 浣跨敤鏂瑰紡锛氭ā鍨嬪湪璋冪敤宸ュ叿鏃跺彲浣跨敤 `mcp:<server>:<tool>`锛堜緥濡?`mcp:calc:calculator`锛夈€?

TTS 璇煶杈撳嚭
- 涓夌妯″紡锛歚openai` / `http` / `command`
  - openai锛氫娇鐢?OpenAI TTS锛堜緥濡?`gpt-4o-mini-tts`锛夈€傞渶瑕佸湪 `api` 涓纭厤缃?Key/URL銆?
  - http锛氬悜鑷缓/绗笁鏂?HTTP 鎺ュ彛鍙戦€?`{"text","voice","format"}`锛屽搷搴斿彲涓洪煶棰戝瓧鑺傛垨 JSON(base64)銆?
  - command锛氭墽琛屾湰鍦板懡浠わ紝灏嗛煶棰戝啓鍏?`{out}` 鎸囧畾璺緞銆傛敮鎸佸崰浣嶇 `{text}/{voice}/{format}/{out}`銆?
- 鐩稿叧閰嶇疆锛堢ず渚嬶級锛?
```
{
  "output": {
    "tts_enable": true,
    "tts_provider": "openai",
    "tts_model": "gpt-4o-mini-tts",
    "tts_voice": "alloy",
    "tts_format": "mp3"
  }
}
```
- 鐢熸垚鐨勯煶棰戞枃浠跺瓨鏀撅細`data/ai_chat/tts/`锛屾秷鎭皢鑷姩鎼哄甫璇煶锛堝叿浣撹閫傞厤鍣ㄨ兘鍔涳級銆?

浼氳瘽涓庤蹇?
- 鍘嗗彶涓庣姸鎬佹寔涔呭寲鍒?SQLite锛氳〃 `ai_chat_sessions`锛堜綅浜?`data/entertain.db`锛夈€?
- `session.max_rounds` 鎺у埗淇濈暀鐨?user+assistant 杞暟锛堟ā鍨嬫秷鎭墠浼氳鍓級銆?
- 缇よ亰鐭湡涓婁笅鏂囷紙鍐呭瓨 LTM锛夛細鎸?`chatroom_history_max_lines` 琛屼繚瀛樷€滄渶杩戠兢鑱婃憳瑕佲€濓紝鐢ㄤ簬涓诲姩鍥炲鎻愮ず銆?
- 鎽樿璁板繂锛?
  - `memory.enable_summarize`: 鍚敤/绂佺敤
  - `memory.summarize_min_rounds`: 寮€濮嬫€荤粨鎵€闇€鏈€灏忚疆鏁?
  - `memory.summarize_interval_rounds`: 闂撮殧杞暟鍐嶆鎬荤粨
  - 鎽樿鍐欏叆浼氳瘽 config_json 鐨?`memory_summary` 瀛楁骞舵敞鍏?System Prompt銆?

鏉冮檺涓庝綔鐢ㄥ煙
- 鎻掍欢榛樿瀵规墍鏈夊満鏅敓鏁堬紙缇?绉侊級銆?
- 鏉冮檺绛夌骇锛堝弬鑰冩湰椤圭洰 PermLevel锛夛細
-  绠＄悊鍛橈細`#娓呯┖浼氳瘽`銆乣#寮€鍚疉I`銆乣#鍏抽棴AI`銆乣#鍒囨崲浜烘牸` 绛?
-  瓒呯锛歚#鏈嶅姟鍟嗗垪琛╜銆乣#鍒囨崲鏈嶅姟鍟哷銆乣#宸ュ叿鍒楄〃`銆乣#寮€鍚?鍏抽棴宸ュ叿`銆乣#寮€鍚?鍏抽棴TTS`銆乣#閲嶈浇AI閰嶇疆`

瀹屾暣閰嶇疆瀛楁閫熻
- `api`: {鍚嶇О: {`base_url`,`api_key`,`model`,`timeout`}}
- `session`: `api_active`,`default_temperature`,`max_rounds`,`chatroom_history_max_lines`,`active_reply_enable`,`active_reply_probability`,`active_reply_prompt_suffix`
- `tools`: `enabled`,`max_iterations`,`builtin_tools`,`mcp_enabled`,`mcp_servers`锛堝惈 `name`,`command`,`args`,`env`锛?
- `output`: `tts_enable`,`tts_provider`,`tts_model`,`tts_voice`,`tts_format`,`tts_http_*`,`tts_command`
- `input`: `image_max_side`,`image_jpeg_quality`
- `memory`: `enable_summarize`,`summarize_min_rounds`,`summarize_interval_rounds`

甯歌闂锛團AQ锛?
- 娌℃湁鍥炲/绌虹櫧锛氭鏌?`config/ai_chat/config.json` 涓?`api` 鏄惁閰嶇疆銆乣session.api_active` 鏄惁鎸囧悜瀛樺湪鐨勬湇鍔″晢銆丄PI Key 鏄惁鏈夋晥銆?
- 鎻愮ず鏈厤缃?OpenAI锛氱涓€娆¤繍琛屼細鍦ㄦ棩蹇椾腑鎻愮ず閰嶇疆鏂囦欢璺緞锛岃鎸夎矾寰勮ˉ鍏ㄩ厤缃苟 `#閲嶈浇AI閰嶇疆`銆?
- 鍥剧墖鏃犳硶璇嗗埆锛氱‘璁ゅ彂閫佺殑鍥剧墖琚€傞厤鍣ㄦ纭В鏋愶紱鎴栧皢鍥剧墖浠?URL 褰㈠紡鍙戦€侊紱蹇呰鏃惰皟楂?`image_max_side`銆?
- 涓诲姩鍥炲澶绻侊細闄嶄綆 `active_reply_probability` 鎴栧叧闂?`active_reply_enable`銆?
- TTS 鏃犲０闊筹細
  - openai锛氱‘璁?`api` 閰嶇疆涓?`tts_model` 鏈夋晥锛涚綉缁滃彲杈俱€?
  - http锛氱‘璁ゆ帴鍙ｈ繑鍥炵被鍨嬩笌 `tts_http_response_type` 鍖归厤锛涘繀瑕佹椂鎵撳嵃鏈嶅姟绔棩蹇楁帓閿欍€?
  - command锛氫繚璇佸懡浠ゅ寘鍚?`{out}` 骞惰兘鍦ㄦ湰鏈哄啓鏂囦欢锛涙鏌ョ敓鎴愯矾寰勪笌鏉冮檺銆?
- MCP 鐪嬩笉鍒板伐鍏凤細纭繚瀹夎 MCP SDK銆佸湪閰嶇疆涓紑鍚?`mcp_enabled` 骞舵纭～鍐?`mcp_servers`锛岄噸杞介厤缃悗鍐嶈瘯銆?

鍏煎鎬т笌娉ㄦ剰浜嬮」
- 鏈彃浠朵娇鐢?OpenAI Chat Completions 椋庢牸鐨勬帴鍙ｏ紱绗笁鏂规湇鍔￠渶鍏煎璇ュ崗璁紙鍚?`tools` 瀛楁锛夈€?
- 杩斿洖鍐呭涓殑鍥剧墖 URL/Markdown 鍥剧墖浼氳鎻愬彇鎴愮嫭绔嬪獟浣撳彂閫侊紝骞朵粠鏂囨湰涓Щ闄ゅ搴旀爣璁般€?
- 鎻掍欢鏂囦欢缁熶竴浣跨敤 UTF-8 缂栫爜锛涜嫢鎺у埗鍙板嚭鐜颁贡鐮侊紝璇峰皢缁堢缂栫爜璁剧疆涓?UTF-8銆?

寮€婧愪笌璐＄尞
- 娆㈣繋鎻愪氦 Issue 涓?PR 鏉ュ畬鍠勫姛鑳戒笌鏂囨。銆?






