# nonebot_plugin_musicshare

一个简单的 NoneBot2 点歌插件：

- 指令：`#点歌 [平台] 关键词`
  - 平台可选：`qq / 酷狗 / 网易 / wyy / kugou / netease`（默认QQ）
- 返回：将搜索结果以图片形式展示，最多 20 条
- 播放：直接发送序号或 `#序号`，例如：`1`、`#1`

依赖：

- nonebot2 + nonebot-adapter-onebot v11（发送语音、分享卡片）
- httpx（网络请求）
- Pillow（图片渲染，用于把歌单渲染成图片）

安装：

1. 将文件夹 `nonebot_plugin_musicshare` 放入机器人项目（或以包形式安装）。
2. 在 `.env.*` 中加入：`plugins = ["nonebot_plugin_musicshare", ...]`。
3. 安装依赖：`pip install httpx Pillow`。

可选配置：

- `MUSIC_WYY_COOKIE`：网易云登录后的 `MUSIC_U` 值，用于官方接口拉取播放链接。若未设置，插件会优先调用公共 API 获取播放链接。

说明：

- 播放链接来自第三方接口，可能失效或不稳定；失败时会降级输出直链文本。
- 若发送语音失败，通常是平台/适配器或链接不支持所致，可查看控制台日志排查。
- 字体渲染会自动从系统常见中文字体中择优加载，若显示为方块或乱码，可自行修改 `__init__.py` 中 `_load_font` 的候选字体路径。
