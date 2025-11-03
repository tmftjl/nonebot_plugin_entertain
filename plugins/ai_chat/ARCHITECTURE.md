AI Chat 插件架构与多模态支持（UTF-8）

目录结构
- commands.py：命令与触发（使用 IO/Multimodal 模块）
- manager.py：核心会话与模型调用（支持图文混合消息）
- models.py：会话数据模型与 JSON 历史
- config.py：配置与人格目录化加载
- tools.py：工具注册/执行（含 image_generate / tts_speak）
- hooks.py：调用前/后钩子
- types.py：通用类型（ChatResult）
- io/extractors.py：OneBot 文本/图片抽取
- multimodal/response_parser.py：解析 Markdown 图片与 data URL → ChatResult
- providers/openai_service.py：OpenAI 辅助能力（文生图、TTS）
- runtime/media/：data URL 解析输出目录（运行时自动创建）

图片输入
- 在消息中附带 `image` 段（可与文本同发）。
- `commands` 通过 `extract_text_and_images` 抽取文本与图片 URL/路径，交由 `manager` 构造多模态 `messages`：
  `[{type:text},{type:image_url}, ...]`（仅在存在图片时）。

多模态输出
- 模型回复中的 Markdown 图片（`![](url)` 或 data URL）由 `response_parser` 自动解析：
  - data URL 会保存至 `runtime/media/` 并转换为图片消息发送。
  - 文本部分以普通文本发送。

内置工具
- `image_generate(prompt, n, size)`：调用文生图返回 URL 或 data URL。
- `tts_speak(text, voice, format)`：合成语音并返回本地音频路径（mp3）。

可扩展性
- 新增输入类型：在 `io/` 下添加解析器并在 `commands` 中接入。
- 新增输出形态：在 `multimodal/` 下扩展解析与渲染策略。
- 新增模型/服务商：在 `providers/` 下添加实现并在 `tools` 或 `manager` 接入。

