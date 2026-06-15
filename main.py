"""
astrbot_plugin_poke_pro v2.5.0
/poke_chuo @某人    — 手动戳人
/poke_chuo QQ号    — 直接戳QQ号
/poke_status       — 查看状态
"""

import re
import time

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register("astrbot_plugin_poke_pro", "bentianjia", "专业戳一戳插件", "2.5.0")
class PokeProPlugin(Star):

    def __init__(self, context: Context):
        super().__init__(context)
        self._last = 0.0
        self._cnt = 0

    def _cfg(self):
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

    async def _cli(self, ev):
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
        cd = self._cfg()["cd"]
        now = time.time()
        if now - self._last < cd:
            return False, f"冷却{cd}s"
        client = await self._cli(ev)
        if not client:
            return False, "QQ未连接"
        try:
            if gid:
                await client.call_action("group_poke", group_id=int(gid), user_id=int(tid))
            else:
                await client.call_action("friend_poke", user_id=int(tid))
            self._last = now
            self._cnt += 1
            return True, ""
        except Exception as e:
            return False, str(e)

    def _txt(self, ev):
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
                    if qq:
                        qqs.append(int(qq))
                elif isinstance(s, dict) and s.get("type") == "at":
                    qq = (s.get("data") or {}).get("qq", "")
                    if qq:
                        qqs.append(int(qq))
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
                if v:
                    return int(v)
        except Exception:
            pass
        return None

    # ── 指令 ────────────────────────────────────────

    @filter.command("poke_chuo")
    async def cmd_poke_chuo(self, event: AstrMessageEvent):
        """戳人: /poke_chuo @某人 或 /poke_chuo QQ号"""
        cfg = self._cfg()
        if not cfg["enable"]:
            yield event.plain_result("❌ 已禁用")
            return
        if cfg["perm"] == "admin" and getattr(event, "role", "") != "admin":
            yield event.plain_result("❌ 仅管理员")
            return

        target = None
        qqs = self._ats(event)
        if qqs:
            target = qqs[0]
        else:
            txt = self._txt(event)
            txt = re.sub(r".*?poke_chuo\s*", "", txt, flags=re.IGNORECASE).strip()
            m = re.search(r"(\d{5,11})", txt)
            if m:
                target = int(m.group(1))

        if not target:
            yield event.plain_result("❌ 用法: /poke_chuo @某人 或 /poke_chuo QQ号")
            return

        gid = self._gid(event)
        ok, err = await self._poke(target, gid, event)
        if ok:
            yield event.plain_result(f"✅ 戳了 QQ:{target}")
        else:
            yield event.plain_result(f"❌ {err}")

    @filter.command("poke_status")
    async def cmd_poke_status(self, event: AstrMessageEvent):
        """状态: /poke_status"""
        cfg = self._cfg()
        cli = await self._cli(event)
        yield event.plain_result(
            f"PokePro v2.5.0 | "
            f"{'🟢' if cfg['enable'] else '🔴'} | "
            f"perm:{cfg['perm']} | "
            f"kw:{'🟢' if cfg['kw_mode'] else '🔴'} | "
            f"cd:{cfg['cd']}s | "
            f"pokes:{self._cnt} | "
            f"QQ:{'🟢' if cli else '🔴'}"
        )
