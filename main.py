"""
astrbot_plugin_poke_pro v4.0.0
/poke chuo @某人 / QQ号  — 手动戳人（静默，QQ 自带提示）
/poke status             — 查看状态
/poke perm all/admin     — 管理员切换权限
/poke keyword on/off     — 关键词开关
/poke cool <秒>         — 冷却时间

被戳反戳: 检测到被戳时概率反戳，更拟人
兼容 astrbot_plugin_pock (zgojin)
"""

import re
import time
import json

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register("astrbot_plugin_poke_pro", "bentianjia", "专业戳一戳插件", "4.0.0")
class PokeProPlugin(Star):

    def __init__(self, context: Context):
        super().__init__(context)
        self._last = 0.0
        self._cnt = 0
        self._last_poke_back = 0.0

    def _get_config(self):
        try: c = getattr(self, "config", None) or {}
        except Exception: c = {}

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
            "cd": int(c.get("poke_cooldown", 10)),
            "poke_back_cooldown": int(c.get("poke_back_cooldown", 30)),
        }

    async def _client(self, ev=None):
        try:
            if ev:
                bot = getattr(ev, "bot", None)
                if bot and hasattr(bot, "call_action"):
                    return bot
        except Exception:
            pass
        return None

    async def _poke(self, tid, gid=None, ev=None):
        cd = self._get_config()["cd"]
        now = time.time()
        if now - self._last < cd:
            return False
        c = await self._client(ev)
        if not c:
            return False
        try:
            if gid:
                await c.call_action("group_poke", group_id=int(gid), user_id=int(tid))
            else:
                await c.call_action("friend_poke", user_id=int(tid))
            self._last = now
            self._cnt += 1
            return True
        except Exception:
            return False

    def _text(self, ev):
        raw = ev.message_obj
        for m in ["get_message", "message_str"]:
            v = getattr(raw, m, None)
            if v is None: continue
            if callable(v): return v() or ""
            return str(v) or ""
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
        except Exception: pass
        return qqs

    def _gid(self, ev):
        try:
            msg = ev.message_obj
            for a in ("group_id", "group_qq", "group_code"):
                v = getattr(msg, a, None)
                if v is not None and str(v).strip(): return int(v)
            if hasattr(ev, "get_group_id"): return ev.get_group_id()
        except Exception: pass
        return None

    def _sid(self, ev):
        try:
            if hasattr(ev, "get_sender_id"): return int(ev.get_sender_id())
            for a in ("sender_id", "user_id", "sender_qq"):
                v = getattr(ev.message_obj, a, None)
                if v: return int(v)
        except Exception: pass
        return None

    def _admin_only(self, event):
        if getattr(event, "role", "") != "admin":
            raise PermissionError("仅管理员")

    def _save(self, key, val):
        try: self.config[key] = val; return True
        except Exception: return False

    # ── 被戳反戳 (LLM 自主决定) ═══════════════════════

    def _is_poke_notice(self, ev):
        raw = ev.message_obj
        for attr in ("notice_type", "post_type"):
            v = getattr(raw, attr, None)
            if v in ("notice", "notify"):
                if getattr(raw, "sub_type", None) == "poke":
                    return True
        if isinstance(raw, dict):
            if raw.get("notice_type") == "notify" and raw.get("sub_type") == "poke":
                return True
            if raw.get("post_type") == "notice" and raw.get("sub_type") == "poke":
                return True
        return False

    async def _ask_llm_poke_back(self, poker_name):
        prompt = f"刚有人戳了你。\n戳你的人: {poker_name}\n\n根据语境决定要不要戳回去。\n只回复一行JSON: {{\"poke_back\": true/false, \"reason\": \"理由\"}}"
        try:
            if hasattr(self.context, "llm_generate"):
                resp = await self.context.llm_generate(prompt=prompt, temperature=0.7)
                return resp.completion_text if resp else None
        except Exception:
            pass
        try:
            provider = None
            if hasattr(self.context, "get_using_provider"):
                provider = self.context.get_using_provider()
            elif hasattr(self.context, "provider_manager"):
                pm = self.context.provider_manager
                provider = getattr(pm, "curr_provider_inst", None)
                if not provider:
                    insts = getattr(pm, "provider_insts", [])
                    provider = insts[0] if insts else None
            if provider and hasattr(provider, "text_chat"):
                resp = await provider.text_chat(prompt=prompt, system_prompt="")
                return resp.completion_text if resp else None
        except Exception:
            pass
        return None

    @filter.regex(r".")
    async def _on_poked_or_keyword(self, event: AstrMessageEvent):
        cfg = self._get_config()
        if not cfg["enable"]:
            return

        # 1. 优先检测是否是被戳事件
        if self._is_poke_notice(event):
            await self._handle_poke_notice(event, cfg)
            return

        # 2. 如果开启了关键词模式，检测语境/文本关键词
        if cfg["kw_mode"] and cfg["kws"]:
            txt = self._text(event).strip().lower()
            if any(k in txt for k in cfg["kws"]):
                uid = self._sid(event)
                gid = self._gid(event)
                if uid:
                    await self._poke(uid, gid, event)
                    logger.info(f"[PokePro] 关键词触发戳一戳: {uid}")

    async def _handle_poke_notice(self, event: AstrMessageEvent, cfg: dict):

        now = time.time()
        if now - self._last_poke_back < cfg["poke_back_cooldown"]:
            return

        raw = event.message_obj
        uid = None
        for a in ("user_id", "sender_id", "operator_id"):
            v = getattr(raw, a, None)
            if v: uid = int(v); break
        gid = self._gid(event)
        if not uid:
            sid = self._sid(event)
            if sid: uid = sid
        if not uid:
            return

        poker_name = str(uid)
        if hasattr(event, "get_sender_name"):
            try: poker_name = event.get_sender_name()
            except: pass

        llm_raw = await self._ask_llm_poke_back(poker_name)
        should_poke = False
        reason = ""
        if llm_raw:
            try:
                data = json.loads(llm_raw.strip())
                should_poke = data.get("poke_back", False)
                reason = data.get("reason", "")
            except Exception:
                if "true" in llm_raw.lower():
                    should_poke = True
                    reason = llm_raw.strip()[:20]

        if should_poke:
            self._last_poke_back = now
            ok = await self._poke(uid, gid, event)
            if ok:
                logger.info(f"[PokePro] LLM反戳 {uid}: {reason}")
        else:
            logger.info(f"[PokePro] LLM决定不反戳 {uid}: {reason}")

    @filter.llm_tool(name="poke_user")
    async def poke_user(self, event: AstrMessageEvent):
        '''当你想根据语境主动戳一戳（Nudge/Poke）当前与你对话的用户时调用此工具。注意，这不会发送文字消息，只会触发QQ的戳一戳动作。'''
        cfg = self._get_config()
        if not cfg["enable"]:
            return "戳一戳失败，插件已关闭。"
            
        uid = self._sid(event)
        gid = self._gid(event)
        if not uid:
            return "无法获取用户ID，戳一戳失败。"
            
        ok = await self._poke(uid, gid, event)
        if ok:
            return "已成功戳了该用户。"
        else:
            return "戳一戳失败，可能平台不支持或处于冷却中。"

    # ── 指令 ══════════════════════════════════════════

    @filter.command("poke chuo")
    async def cmd_poke_chuo(self, event: AstrMessageEvent):
        cfg = self._get_config()
        if not cfg["enable"]:
            return  # 静默，不回复
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
            return  # 静默
        gid = self._gid(event)
        ok = await self._poke(target, gid, event)
        if not ok:
            yield event.plain_result("戳失败")

    @filter.command("poke status")
    async def cmd_poke_status(self, event: AstrMessageEvent):
        cfg = self._get_config()
        cli = await self._client(event)
        yield event.plain_result(
            f"PokePro v4.0.0 | {'🟢' if cfg['enable'] else '🔴'} | "
            f"perm:{cfg['perm']} | kw:{'🟢' if cfg['kw_mode'] else '🔴'} | "
            f"cd:{cfg['cd']}s | pokes:{self._cnt} | "
            f"反戳:LLM决策 | "
            f"QQ:{'🟢' if cli else '🔴'}"
        )

    @filter.command("poke perm")
    async def cmd_poke_perm(self, event: AstrMessageEvent):
        try: self._admin_only(event)
        except PermissionError: yield event.plain_result("仅管理员"); return
        txt = self._text(event).strip().lower()
        if "all" in txt:
            yield event.plain_result("-> 所有人" if self._save("poke_permission", "all") else "失败")
        elif "admin" in txt:
            yield event.plain_result("-> 管理员" if self._save("poke_permission", "admin") else "失败")
        else:
            yield event.plain_result("/poke perm all|admin")

    @filter.command("poke keyword")
    async def cmd_poke_keyword(self, event: AstrMessageEvent):
        try: self._admin_only(event)
        except PermissionError: yield event.plain_result("仅管理员"); return
        txt = self._text(event).strip().lower()
        if "on" in txt:
            yield event.plain_result("kw -> 开" if self._save("keyword_mode", True) else "失败")
        elif "off" in txt:
            yield event.plain_result("kw -> 关" if self._save("keyword_mode", False) else "失败")
        else:
            yield event.plain_result("/poke keyword on|off")

    @filter.command("poke cool")
    async def cmd_poke_cool(self, event: AstrMessageEvent):
        try: self._admin_only(event)
        except PermissionError: yield event.plain_result("仅管理员"); return
        txt = self._text(event).strip()
        m = re.search(r"(\d+)", txt)
        if m and 3 <= int(m.group(1)) <= 120:
            yield event.plain_result(f"cd -> {m.group(1)}s" if self._save("poke_cooldown", int(m.group(1))) else "失败")
        else:
            yield event.plain_result("/poke cool 3-120")

    @filter.command("poke back")
    async def cmd_poke_back(self, event: AstrMessageEvent):
        """ /poke back 0-100 设置反戳概率 """
        try: self._admin_only(event)
        except PermissionError: yield event.plain_result("仅管理员"); return
        txt = self._text(event).strip()
        m = re.search(r"(\d+)", txt)
        if m and 0 <= int(m.group(1)) <= 100:
            p = int(m.group(1)) / 100.0
            yield event.plain_result(f"反戳 -> {m.group(1)}%" if self._save("poke_back_prob", p) else "失败")
        else:
            yield event.plain_result("/poke back 0-100  如 /poke back 50")
