from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.api import (
    config_dir,
    plugin_resource_dir,
    plugin_data_dir,
    register_plugin_config,
    register_plugin_schema,
    register_reload_callback,
)


CFG_DIR = config_dir("df")
CFG_PATH = CFG_DIR / "config.json"
RES_DF_DIR = plugin_resource_dir("df")
POKE_DIR = RES_DF_DIR / "poke"
DATA_DF_DIR = plugin_data_dir("df")


DEFAULT_CFG: Dict[str, Any] = {
    "random_picture_open": True,
    # DF 琛ㄦ儏鍥惧簱锛堟埑涓€鎴冲浘鐗囷級浠撳簱鍦板潃
    "poke_repo": "https://cnb.cool/denfenglai/poke.git",
    "poke": {
        "chuo": True,
        "mode": "random",  # image | text | mix | random
        "imageType": "all",  # 鍚嶇О鎴?all
        "imageBlack": [],
        "textMode": "hitokoto",  # hitokoto | list
        "hitokoto_api": "https://v1.hitokoto.cn/?encode=text",
        "textList": [],
    },
    "send_master": {
        "open": True,
        "success": "宸插皢淇℃伅杞彂缁欎富浜?,
        "failed": "鍙戦€佸け璐ワ紝璇风◢鍚庨噸璇?,
        "reply_prefix": "涓讳汉鍥炲锛?,
    },
    "api_urls": {
        "jk_api": "https://api.suyanw.cn/api/jk.php",
        "ql_api": "https://api.suyanw.cn/api/ql.php",
        "lsp_api": "https://api.suyanw.cn/api/lsp.php",
        "zd_api": "https://imgapi.cn/api.php?zd=302&fl=meizi&gs=json",
        "fallback_api": "https://ciallo.hxxn.cc/?name={name}",
    }\r\n

def _validate_cfg(cfg: Dict[str, Any]) -> None:
    def _type(name: str, exp, cond=True):
        if not cond:
            return
        if name in cfg and not isinstance(cfg[name], exp):
            raise ValueError(f"{name} must be {exp}")

    _type("random_picture_open", bool)
    _type("poke_repo", str)

    poke = cfg.get("poke", {})
    if poke and not isinstance(poke, dict):
        raise ValueError("poke must be object")
    if isinstance(poke, dict):
        if "chuo" in poke and not isinstance(poke["chuo"], bool):
            raise ValueError("poke.chuo must be bool")
        if "mode" in poke:
            if poke["mode"] not in {"random", "image", "text", "mix"}:
                raise ValueError("poke.mode invalid")
        if "imageType" in poke and not isinstance(poke["imageType"], str):
            raise ValueError("poke.imageType must be str")
        if "imageBlack" in poke and not isinstance(poke["imageBlack"], list):
            raise ValueError("poke.imageBlack must be list")
        if "textMode" in poke and poke["textMode"] not in {"hitokoto", "list"}:
            raise ValueError("poke.textMode invalid")
        if "hitokoto_api" in poke and not isinstance(poke["hitokoto_api"], str):
            raise ValueError("poke.hitokoto_api must be str")
        if "textList" in poke and not isinstance(poke["textList"], list):
            raise ValueError("poke.textList must be list")

    sm = cfg.get("send_master", {})
    if sm and not isinstance(sm, dict):
        raise ValueError("send_master must be object")
    if isinstance(sm, dict):
        if "open" in sm and not isinstance(sm["open"], bool):
            raise ValueError("send_master.open must be bool")
        for k in ("success", "failed", "reply_prefix"):
            if k in sm and not isinstance(sm[k], str):
                raise ValueError(f"send_master.{k} must be str")

    # 楠岃瘉鏂板鐨?api_urls
    api_urls = cfg.get("api_urls", {})
    if api_urls and not isinstance(api_urls, dict):
        raise ValueError("api_urls must be object")

# 娉ㄥ唽鎻掍欢閰嶇疆
REG = register_plugin_config("df", DEFAULT_CFG, validator=_validate_cfg)

# 妯″潡绾х紦瀛?
_CACHED: Dict[str, Any] = REG.load()


def reload_cache() -> None:
    """閲嶆柊鍔犺浇閰嶇疆鍒版ā鍧楃骇缂撳瓨锛屼緵妗嗘灦閲嶈浇閰嶇疆鏃惰皟鐢ㄣ€?""
    global _CACHED
    _CACHED = REG.load()
    from nonebot import logger
    logger.info(f"[DF] 閰嶇疆宸查噸杞? send_master.success = {_CACHED.get('send_master', {}).get('success', '鏈缃?)}")


# 娉ㄥ唽閲嶈浇鍥炶皟
register_reload_callback("df", reload_cache)

# Schema for frontend (Chinese labels and help)
DF_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "DF 鎻掍欢閰嶇疆",
    "properties": {
        "random_picture_open": {
            "type": "boolean",
            "title": "鍚敤闅忔満鍥剧墖",
            "description": "鍚敤鍚庡搷搴斺€樻潵寮?鐪嬬湅/闅忔満 + 鍏抽敭璇嶁€欑瓑闅忔満鍥剧墖鍛戒护锛屼互鍙婃湰鍦拌〃鎯呭簱",
            "default": True,
            "x-group": "闅忔満鍥剧墖",
            "x-order": 1,
        },
        "poke_repo": {
            "type": "string",
            "title": "琛ㄦ儏鍥惧簱浠撳簱",
            "description": "DF 琛ㄦ儏鍥惧簱锛堟埑涓€鎴冲浘鐗囷級Git 浠撳簱鍦板潃锛岀敤浜庢洿鏂版湰鍦拌祫婧?,
            "default": "https://cnb.cool/denfenglai/poke.git",
            "x-group": "闅忔満鍥剧墖",
            "x-order": 2,
        },
        "poke": {
            "type": "object",
            "title": "鎴充竴鎴冲洖澶?,
            "description": "閰嶇疆鏀跺埌鎴充竴鎴虫椂鐨勫浘鐗?鏂囨湰鍥炲绛栫暐",
            "x-group": "鎴充竴鎴?,
            "x-order": 10,
            "properties": {
                "chuo": {
                    "type": "boolean",
                    "title": "鍚敤鎴充竴鎴?,
                    "description": "鏄惁鍝嶅簲鎴充竴鎴充簨浠?,
                    "default": True,
                    "x-order": 1,
                },
                "mode": {
                    "type": "string",
                    "title": "鍥炲妯″紡",
                    "description": "random=闅忔満 image/text/mix 涓夌涔嬩竴锛沬mage=浠呭浘鐗囷紱text=浠呮枃鏈紱mix=鍥炬枃",
                    "enum": ["random", "image", "text", "mix"],
                    "default": "random",
                    "x-order": 2,
                },
                "imageType": {
                    "type": "string",
                    "title": "鍥剧墖绫诲瀷/琛ㄦ儏鍚?,
                    "description": "all 琛ㄧず浠绘剰鏈湴琛ㄦ儏锛涙垨鎸囧畾鏌愪釜琛ㄦ儏鐩綍鍚?,
                    "default": "all",
                    "x-order": 3,
                },
                "imageBlack": {
                    "type": "array",
                    "title": "灞忚斀琛ㄦ儏",
                    "description": "涓嶅弬涓庨殢鏈虹殑琛ㄦ儏鍚嶇О鍒楄〃",
                    "items": {"type": "string"},
                    "default": [],
                    "x-order": 4,
                },
                "textMode": {
                    "type": "string",
                    "title": "鏂囨湰鏉ユ簮",
                    "description": "hitokoto=闅忔満涓€瑷€; list=浠庤嚜瀹氫箟鍒楄〃闅忔満",
                    "enum": ["hitokoto", "list"],
                    "default": "hitokoto",
                    "x-order": 5,
                },
                "hitokoto_api": {
                    "type": "string",
                    "title": "涓€瑷€ API",
                    "description": "褰撴枃鏈潵婧愪负 hitokoto 鏃惰皟鐢ㄧ殑 API",
                    "default": "https://v1.hitokoto.cn/?encode=text",
                    "x-order": 6,
                },
                "textList": {
                    "type": "array",
                    "title": "鑷畾涔夋枃鏈垪琛?,
                    "description": "褰撴枃鏈潵婧愪负 list 鏃讹紝浠庤鍒楄〃涓殢鏈洪€夋嫨",
                    "items": {"type": "string"},
                    "default": [],
                    "x-order": 7,
                },
            },
        },
        "send_master": {
            "type": "object",
            "title": "杞彂缁欎富浜?,
            "description": "閮ㄥ垎鍛戒护鐨勫弽棣堝皢杞彂缁欎富浜鸿处鍙凤紝鍙厤缃鐜囦笌鎻愮ず鏂囧瓧",
            "x-group": "涓讳汉杞彂",
            "x-order": 20,
            "properties": {
                "open": {
                    "type": "boolean",
                    "title": "鍚敤",
                    "description": "鏄惁寮€鍚浆鍙戠粰涓讳汉",
                    "default": True,
                    "x-order": 1,
                },
                "success": {
                    "type": "string",
                    "title": "鎴愬姛鎻愮ず",
                    "description": "杞彂鎴愬姛鏃剁粰鐢ㄦ埛鐨勬彁绀鸿",
                    "default": "宸插皢淇℃伅杞彂缁欎富浜?,
                    "x-order": 2,
                },
                "failed": {
                    "type": "string",
                    "title": "澶辫触鎻愮ず",
                    "description": "杞彂澶辫触鏃剁粰鐢ㄦ埛鐨勬彁绀鸿",
                    "default": "鍙戦€佸け璐ワ紝璇风◢鍚庨噸璇?,
                    "x-order": 3,
                },
                "reply_prefix": {
                    "type": "string",
                    "title": "鍥炲鍓嶇紑",
                    "description": "涓讳汉鍥炲鐢ㄦ埛鏃剁殑鍓嶇紑鏂囧瓧",
                    "default": "涓讳汉鍥炲锛?,
                    "x-order": 4,
                },
            },
        },
        "api_urls": {
            "type": "object",
            "title": "API鍦板潃閰嶇疆",
            "description": "闅忔満鍥剧墖绛夊姛鑳戒娇鐢ㄧ殑绗笁鏂笰PI鍦板潃",
            "x-group": "API閰嶇疆",
            "x-order": 30,
            "x-collapse": True,
            "properties": {
                "jk_api": {
                    "type": "string",
                    "title": "JK鍥続PI",
                    "description": "闅忔満JK鍥剧墖API鍦板潃",
                    "default": "https://api.suyanw.cn/api/jk.php",
                    "x-order": 1,
                },
                "ql_api": {
                    "type": "string",
                    "title": "娓呭喎鍥続PI",
                    "description": "闅忔満娓呭喎鍥剧墖API鍦板潃",
                    "default": "https://api.suyanw.cn/api/ql.php",
                    "x-order": 2,
                },
                "lsp_api": {
                    "type": "string",
                    "title": "LSP鍥続PI",
                    "description": "闅忔満LSP鍥剧墖API鍦板潃",
                    "default": "https://api.suyanw.cn/api/lsp.php",
                    "x-order": 3,
                },
                "zd_api": {
                    "type": "string",
                    "title": "鎸囧畾鍥続PI",
                    "description": "闅忔満鎸囧畾绫诲瀷鍥剧墖API鍦板潃",
                    "default": "https://imgapi.cn/api.php?zd=302&fl=meizi&gs=json",
                    "x-order": 4,
                },
                "fallback_api": {
                    "type": "string",
                    "title": "澶囩敤鍥続PI",
                    "description": "涓籄PI澶辫触鏃剁殑澶囩敤鍥剧墖API锛寋name}浼氳鏇挎崲涓哄浘鐗囩被鍨?,
                    "default": "https://ciallo.hxxn.cc/?name={name}",
                    "x-order": 5,
                },
            },
        }\r\n
try:
    register_plugin_schema("df", DF_SCHEMA)
except Exception:
    pass


def ensure_dirs() -> None:
    RES_DF_DIR.mkdir(parents=True, exist_ok=True)
    POKE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DF_DIR.mkdir(parents=True, exist_ok=True)


def load_cfg() -> Dict[str, Any]:
    """浠庢ā鍧楃骇缂撳瓨璇诲彇閰嶇疆銆?""
    ensure_dirs()
    return _CACHED


def save_cfg(cfg: Dict[str, Any]) -> None:
    """淇濆瓨閰嶇疆骞舵洿鏂版ā鍧楃骇缂撳瓨銆?""
    ensure_dirs()
    REG.save(cfg)
    # 淇濆瓨鍚庣珛鍗虫洿鏂扮紦瀛?
    reload_cache()


def face_list() -> List[str]:
    """杩斿洖 resource/df/poke 涓嬪彲鐢ㄧ殑琛ㄦ儏鍖呭悕绉板垪琛ㄣ€?""
    ensure_dirs()
    names: List[str] = []
    try:
        for p in POKE_DIR.iterdir():
            if p.is_dir() and p.name != ".git":
                names.append(p.name)
    except Exception:
        pass
    return sorted(set(names or ["default"]))


def random_local_image(face: str) -> Optional[Path]:
    """浠庢湰鍦拌〃鎯呭寘鐩綍闅忔満閫夋嫨涓€涓枃浠惰矾寰勶紝鑻ヤ笉瀛樺湪鍒欒繑鍥?None銆?""
    d = POKE_DIR / face
    if not d.exists() or not d.is_dir():
        return None
    try:
        files = [p for p in d.iterdir() if p.is_file()]
        if not files:
            return None
        import random

        return random.choice(files)
    except Exception:
        return None





