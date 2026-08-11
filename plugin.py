"""maibot-highrisk-blocker — 高危错误消息拦截插件

订阅 `send_service.before_send` Hook，在消息真正发往平台前检查文本内容。

背景：部分 LLM 中转代理会把上游内容安全拒绝返回的原始错误文案
（如 `The request was rejected because it was considered high risk`）
**当作正常模型响应**返回，MaiBot 会误认为这是模型回复并原样发到群里。

处理策略（按命中短语逐个清理）：
1. 从消息文本段中移除所有命中的短语；
2. 若清理后仍残留命中短语（如整条消息就是错误原文）→ 中止发送；
3. 若清理后仍有正常文本 → 发送清理后的内容，保留正常回复。
"""

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Field, MaiBotPlugin, PluginConfigBase
from maibot_sdk.components import HookHandler, HookMode, HookOrder

DEFAULT_PHRASES = [
    "The request was rejected because it was considered high risk",
    "considered high risk",
]


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置节。"""

    __ui_label__ = "插件"

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default="1.0.0", description="配置版本")


class BlockerSectionConfig(PluginConfigBase):
    """高危错误消息拦截配置节。"""

    __ui_label__ = "拦截配置"
    __ui_icon__ = "shield"
    __ui_order__ = 1

    enabled: bool = Field(default=True, description="是否启用高危错误消息拦截")
    phrases: list[str] = Field(
        default_factory=lambda: list(DEFAULT_PHRASES),
        description="消息文本命中以下任意片段（不区分大小写）时移除该片段；移除后无剩余内容则中止发送",
    )


class BlockerConfig(PluginConfigBase):
    """拦截插件配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    blocker: BlockerSectionConfig = Field(default_factory=BlockerSectionConfig)


class HighRiskBlockerPlugin(MaiBotPlugin):
    """在发送前清理/拦截高危错误消息的插件"""

    config_model = BlockerConfig

    async def on_load(self) -> None:
        """插件加载完成后的初始化。"""
        self.ctx.logger.info(
            "[highrisk-blocker] 已加载，启用状态=%s，拦截片段=%d 条",
            self.config.blocker.enabled,
            len([p for p in self.config.blocker.phrases if str(p or "").strip()]),
        )

    async def on_unload(self) -> None:
        """插件卸载时的清理。"""
        self.ctx.logger.info("[highrisk-blocker] 已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        """插件配置热更新回调。"""
        if scope == CONFIG_RELOAD_SCOPE_SELF:
            self.ctx.logger.info(
                "[highrisk-blocker] 配置已更新: version=%s，启用状态=%s，拦截片段=%d 条",
                version,
                self.config.blocker.enabled,
                len([p for p in self.config.blocker.phrases if str(p or "").strip()]),
            )

    @HookHandler(
        "send_service.before_send",
        name="high_risk_blocker",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        description="移除出站消息中的高危错误文案，无剩余内容时中止发送",
    )
    async def block_high_risk(self, **kwargs):
        """检查待发送消息，命中关键词则移除或中止。"""
        if not self.config.blocker.enabled:
            return {"action": "continue", "modified_kwargs": kwargs}

        message = kwargs.get("message") or {}
        if not isinstance(message, dict):
            return {"action": "continue", "modified_kwargs": kwargs}

        phrases = [
            str(phrase).strip().lower()
            for phrase in self.config.blocker.phrases
            if str(phrase or "").strip()
        ]
        if not phrases:
            return {"action": "continue", "modified_kwargs": kwargs}

        raw_message = message.get("raw_message")
        if not isinstance(raw_message, list):
            return {"action": "continue", "modified_kwargs": kwargs}

        cleaned = False
        new_raw: list[dict] = []
        for segment in raw_message:
            if not isinstance(segment, dict):
                new_raw.append(segment)
                continue
            if segment.get("type") != "text" or not isinstance(segment.get("data"), str):
                new_raw.append(segment)
                continue

            text = segment["data"]
            lowered = text.lower()
            if not any(phrase in lowered for phrase in phrases):
                new_raw.append(segment)
                continue

            # 移除所有命中短语，保留其余正常内容
            cleaned_text = text
            for phrase in phrases:
                if phrase in cleaned_text.lower():
                    cleaned_text = self._remove_case_insensitive(cleaned_text, phrase)
                    cleaned = True
            if cleaned_text.strip():
                new_raw.append({"type": "text", "data": cleaned_text.strip()})

        if not cleaned:
            return {"action": "continue", "modified_kwargs": kwargs}

        # 清理后没有任何剩余文本段 -> 整条消息就是错误原文，中止发送
        remaining = [s for s in new_raw if s.get("type") == "text" and str(s.get("data") or "").strip()]
        if not remaining:
            self.ctx.logger.info("[highrisk-blocker] 已拦截整条高危错误消息")
            return {"action": "abort"}

        self.ctx.logger.info("[highrisk-blocker] 已从消息中移除高危错误文案")
        message["raw_message"] = new_raw
        processed = message.get("processed_plain_text")
        if isinstance(processed, str):
            cleaned_processed = processed
            for phrase in phrases:
                cleaned_processed = self._remove_case_insensitive(cleaned_processed, phrase)
            message["processed_plain_text"] = cleaned_processed.strip()
        return {"action": "continue", "modified_kwargs": kwargs}

    @staticmethod
    def _remove_case_insensitive(text: str, phrase: str) -> str:
        """从文本中删除全部命中短语（不区分大小写）。"""
        lowered_text = text.lower()
        out: list[str] = []
        cursor = 0
        while True:
            index = lowered_text.find(phrase, cursor)
            if index < 0:
                out.append(text[cursor:])
                break
            out.append(text[cursor:index])
            cursor = index + len(phrase)
        return "".join(out)


def create_plugin() -> HighRiskBlockerPlugin:
    """创建拦截插件实例。"""
    return HighRiskBlockerPlugin()
