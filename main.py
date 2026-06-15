"""
astrbot_plugin_poke_pro - 专业戳一戳插件
/poke chuo @某人 / QQ号  — 手动戳人
/poke status             — 查看状态
/poke perm all/admin     — 管理员切换权限
"""

import re
import time

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register("astrbot_plugin_poke_pro", "bentianjia", "专业戳一戳插件", "3.1.0")
class PokeProPlugin(Star):

    def __init__(self, context: Context):
        super().__init__(context)
        self._last = 0.0
        self._cnt = 0

    def _get_config(self):
        try:
            c = getattr(self, "config", None) or {}
        except Exception:
            c = {}
        kw = c.get("context_aware_keywords", "")
        if isinstance(kw, list):
            kws = [k.strip().lower() for k in kw if k.strip()]
        else:
            kws = [k.strip().lower() for k in kw.split(",") if k.strip()]
        return {
            "enable": c.get("enable", True),
            "kw_mode": c.get("keyword_mode", True),
            "perm": c.get("poke_permission", "all"),
            "kws": kws,
            "reply": c.get("context_aware_reply", True),
            "cd": int(c.get("poke_cooldown", 10)),
        }

    async def _client(self, ev=None):
        try:
            if ev:
                for a in ("_platform", "platform"):
                    p = getattr(ev, a, None)
                    if p:
                        c = getattr(p, "client", None)
                        if c and hasattr(c, "call_action"):
                            return c
            pm = getattr(self.context, "platform_manager", None)
            if pm:
                for lst in [getattr(pm, "adapters", None), getattr(pm, "sessions", None)]:
                    if lst:
                        for x in lst:
                            a = getattr(x, "platform", x)
                            c = getattr(a, "client", None)
                            if c and hasattr(c, "call_action"):
                                return c
        except Exception:
            pass
        return None

    async def _poke(self, tid, gid=None, ev=None):
        cd = self._get_config()["cd"]
        now = time.time()
        if now - self._last < cd:
            return False, f"冷却{cd}s"
        c = await self._client(ev)
        if not c:
            return False, "QQ未连接"
        try:
            if gid:
                await c.call_action("group_poke", group_id=int(gid), user_id=int(tid))
            else:
                await c.call_action("friend_poke", user_id=int(tid))
            self._last = now
            self._cnt += 1
            return True, ""
        except Exception as e:
            return False, str(e)

    def _text(self, ev):
        raw = ev.message_obj
        for m in ["get_message", "message_str"]:
            if hasattr(raw, m):
                return getattr(raw, m)() or ""
        return str(raw) if raw else ""

    def _ats(self, ev):
        qqs = []
        try:
            segs = getattr(ev.message_obj, "message", None) or []
            for s in segs:
                if str(getattr(s, "type", "")) == "at":
                    qq = (getattr(s, "data", {}) or {}).get("qq", "")
                    if qq: qqs.append(int(qq))
                elif isinstance(s, dict) and s.get("type") == "at":
                    qq = (s.get("data") or {}).get("qq", "")
                    if qq: qqs.append(int(qq))
        except Exception:
            pass
        return qqs

    def _gid(self, ev):
        try:
            msg = ev.message_obj
            for a in ("group_id", "group_qq", "group_code"):
                v = getattr(msg, a, None)
                if v is not None and str(v).strip():
                    return int(v)
            if hasattr(ev, "get_group_id"):
                return ev.get_group_id()
        except Exception:
            pass
        return None

    def _sid(self, ev):
        try:
            if hasattr(ev, "get_sender_id"):
                return int(ev.get_sender_id())
            for a in ("sender_id", "user_id", "sender_qq"):
                v = getattr(ev.message_obj, a, None)
                if v: return int(v)
        except Exception:
            pass
        return None

    @filter.command("poke chuo")
    async def cmd_poke_chuo(self, event: AstrMessageEvent):
        cfg = self._get_config()
        if not cfg["enable"]:
            yield event.plain_result("已禁用")
            return
        if cfg["perm"] == "admin" and getattr(event, "role", "") != "admin":
            yield event.plain_result("仅管理员可用")
            return
        target = None
        qqs = self._ats(event)
        if qqs:
            target = qqs[0]
        else:
            txt = self._text(event)
            txt = re.sub(r".*?poke\s+chuo\s*", "", txt, flags=re.IGNORECASE).strip()
            m = re.search(r"(\d{5,11})", txt)
            if m: target = int(m.group(1))
        if not target:
            yield event.plain_result("/poke chuo @某人 或 /poke chuo QQ号")
            return
        gid = self._gid(event)
        ok, err = await self._poke(target, gid, event)
        if ok:
            yield event.plain_result(f"戳了 QQ:{target}")
        else:
            yield event.plain_result(f"失败: {err}")

    @filter.command("poke status")
    async def cmd_poke_status(self, event: AstrMessageEvent):
        cfg = self._get_config()
        cli = await self._client(event)
        yield event.plain_result(
            f"PokePro v3.1.0 | {'🟢' if cfg['enable'] else '🔴'} | "
            f"perm:{cfg['perm']} | kw:{'🟢' if cfg['kw_mode'] else '🔴'} | "
            f"cd:{cfg['cd']}s | pokes:{self._cnt} | "
            f"QQ:{'🟢' if cli else '🔴'}"
        )

    def _admin_only(self, event):
        if getattr(event, "role", "") != "admin":
            raise PermissionError("仅管理员可用")

    def _save(self, key, val):
        try:
            self.config[key] = val
            return True
        except Exception:
            return False

    @filter.command("poke perm")
    async def cmd_poke_perm(self, event: AstrMessageEvent):
        """ /poke perm all|admin """
        try:
            self._admin_only(event)
        except PermissionError:
            yield event.plain_result("仅管理员可用")
            return
        txt = self._text(event).strip().lower()
        if "all" in txt:
            yield event.plain_result("主动戳人 -> 所有人可用" if self._save("poke_permission", "all") else "保存失败")
        elif "admin" in txt:
            yield event.plain_result("主动戳人 -> 仅管理员" if self._save("poke_permission", "admin") else "保存失败")
        else:
            yield event.plain_result("/poke perm all 或 /poke perm admin")

    @filter.command("poke keyword")
    async def cmd_poke_keyword(self, event: AstrMessageEvent):
        """ /poke keyword on|off """
        try:
            self._admin_only(event)
        except PermissionError:
            yield event.plain_result("仅管理员可用")
            return
        txt = self._text(event).strip().lower()
        if "on" in txt:
            yield event.plain_result("关键词自动戳 -> 开" if self._save("keyword_mode", True) else "保存失败")
        elif "off" in txt:
            yield event.plain_result("关键词自动戳 -> 关" if self._save("keyword_mode", False) else "保存失败")
        else:
            yield event.plain_result("/poke keyword on 或 /poke keyword off")

    @filter.command("poke cool")
    async def cmd_poke_cool(self, event: AstrMessageEvent):
        """ /poke cool <秒数> """
        try:
            self._admin_only(event)
        except PermissionError:
            yield event.plain_result("仅管理员可用")
            return
        txt = self._text(event).strip()
        m = re.search(r"(\d+)", txt)
        if m:
            s = int(m.group(1))
            if 3 <= s <= 120:
                yield event.plain_result(f"冷却 -> {s}s" if self._save("poke_cooldown", s) else "保存失败")
            else:
                yield event.plain_result("3-120秒之间")
        else:
            yield event.plain_result("/poke cool <秒数> 如 /poke cool 30")
