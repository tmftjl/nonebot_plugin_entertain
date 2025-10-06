Put face-pack folders under this directory:

- nonebot_plugin_entertain/resource/df/poke/<pack_name>/*

Each pack is a folder containing images. The plugin will scan folder names
as face types and randomly pick an image from the chosen pack. If no local
image exists, it falls back to a remote image provider.

DF gallery update commands (superuser by default):
- Install gallery: send `#DF安装图库`
- Update gallery: send `#DF更新图库` or `#DF强制更新图库`
Repo can be changed via `DEFAULT_CFG['poke_repo']` in `plugins/df/config.py`.
