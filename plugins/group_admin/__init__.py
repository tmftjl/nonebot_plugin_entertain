from __future__ import annotations

"""缇ょ鎻掍欢鍏ュ彛

鎸夊姛鑳芥媶鍒嗕负澶氫釜妯″潡锛岄伩鍏嶅懡浠ゆ尋鍦ㄤ竴涓枃浠讹細
- basic锛氶€€缇?鏀圭兢鍚嶇墖/鏀圭兢鍚嶇О/缇ゅ垪琛?鎸夊簭鍙风兢鍙?
- mute锛氱瑷€/瑙ｇ/鍏ㄤ綋绂佽█
- admin_ops锛氳缃?鍙栨秷绠＄悊鍛樸€佽涪浜?鎷夐粦韪?
- message_ops锛氭挙鍥炪€佽绮惧崕/鍙栨秷绮惧崕
- banwords锛氳繚绂佽瘝寮€鍏炽€佸鍒犳竻銆佸垪琛ㄣ€佸姩浣滀笌鎷︽埅
"""

from ...core.api import Plugin
from ...core.framework.perm import PermLevel, PermScene

# 寤虹珛鎻掍欢绾ч粯璁ら」锛堜粎涓€娆★級锛涘瓙妯″潡涓娇鐢?Plugin() 鍗冲彲娉ㄥ唽鍛戒护
_P = Plugin(name="group_admin", display_name="缇ょ", enabled=True, level=PermLevel.LOW, scene=PermScene.ALL)

# 瀵煎叆瀛愭ā鍧椾互娉ㄥ唽鍏跺懡浠ゅ拰鎷︽埅鍣?
from . import mute as _mute  # noqa: F401
from . import admin_ops as _admin_ops  # noqa: F401
from . import message_ops as _message_ops  # noqa: F401
from . import banwords as _banwords  # noqa: F401


