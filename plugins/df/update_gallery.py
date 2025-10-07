from __future__ import annotations

import re
import asyncio
import subprocess
from typing import Tuple

from nonebot import on_regex
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent

from ...perm import permission_for_cmd
from .config import load_cfg, POKE_DIR, RES_DF_DIR


_cfg = load_cfg()
_updating_gallery = False


_UPDATE = on_regex(
    r"^#?DF(?:安装|(?:强制)?更新)(?:\u6233\u4e00\u6233)?图库$",
    priority=12,
    block=True,
    permission=permission_for_cmd("df", "update_gallery"),
)


async def _run_git(cmd: str, cwd) -> Tuple[int, str, str]:
    def _run():
        p = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    return await asyncio.to_thread(_run)


@_UPDATE.handle()
async def _(matcher: Matcher, event: MessageEvent):
    global _updating_gallery
    if _updating_gallery:
        await matcher.finish("已有更新任务正在进行中，请勿重复操作~")
    _updating_gallery = True
    try:
        msg = str(event.get_message())
        force = "强制" in msg
        repo = str(_cfg.get("poke_repo", "https://cnb.cool/denfenglai/poke.git"))
        # Case 1: existing git repo -> update
        if POKE_DIR.exists() and (POKE_DIR / ".git").exists():
            await matcher.send(f"开始{'强制' if force else ''}更新图库啦，请稍安勿躁~")
            cmd = "git reset --hard origin/main && git pull --rebase" if force else "git pull --rebase"
            code, out, err = await _run_git(cmd, POKE_DIR)
            if code != 0:
                detail = (err or out).strip()
                await matcher.finish(
                    f"图片资源更新失败！\nError code: {code}\n{detail}\n可尝试使用 #DF强制更新图库，或执行 #DF安装图库 重新初始化。"
                )
            if ("Already up to date" in out) or ("最新" in out):
                await matcher.finish("目前所有图片都已经是最新了~")
            m = re.search(r"(\\d+) files changed", out)
            if m:
                await matcher.finish(f"更新成功，共更新 {m.group(1)} 张图片~")
            await matcher.finish("戳一戳图片资源更新完毕")

        # Case 2: folder exists but not a git repo -> do not auto init (by request)
        if POKE_DIR.exists() and not (POKE_DIR / ".git").exists():
            await matcher.finish(
                "检测到图库目录存在但不是 Git 仓库。\n"
                "如需通过命令更新，请手动清空/删除该目录后发送 #DF安装图库；\n"
                "也可自行管理本地图片目录，直接使用 #随机<表情名>。"
            )

        # Case 3: fresh install (no folder)
        if not POKE_DIR.exists():
            await matcher.send("开始安装戳一戳图库，可能需要一段时间，请稍安勿躁~")
            cmd = f"git clone --depth=1 {repo} poke"
            code, out, err = await _run_git(cmd, RES_DF_DIR)
            if code != 0:
                detail = (err or out).strip()
                await matcher.finish(
                    f"戳一戳图库安装失败！\nError code: {code}\n{detail}\n请稍后重试。"
                )
            await matcher.finish("戳一戳图库安装成功！您后续也可以通过 #DF更新图库 命令来更新图片")
    finally:
        _updating_gallery = False
