# Highrisk Blocker for MaiBot

MaiBot 高危错误消息拦截插件：在**出站消息发送前**移除或拦截包含高危错误文案的消息，避免 LLM 返回的错误原文被直接发到群里。

## 背景

部分 LLM 中转代理会把上游**内容安全拒绝**返回的原始错误文案（如
`The request was rejected because it was considered high risk`）
**当作正常的模型响应**返回（HTTP 200）。MaiBot 会把这段错误原文误认为是
模型回复，原样发送到 QQ 群 / 频道，造成刷屏。

本插件订阅 `send_service.before_send` Hook —— 所有出站消息的最后闸口，
在消息真正发往平台前做检查，从根源上拦下这类错误文案。

## 功能特性

- 🛡️ **发送前拦截**：在消息真正发出前检查，命中高危文案的消息不会被发到群里
- ✂️ **混合消息只删错误**：若错误文案混在正常回复末尾，只移除错误片段，正常内容照常发送
- 🚫 **整条错误直接中止**：若整条消息就是错误原文，直接中止发送
- 🎯 **不区分大小写**：英文大小写变体均能命中
- 🔧 **自动配置初始化**：首次启动自动生成 `config.toml`，不覆盖已有配置

## 安装

### 1. 复制插件到 MaiBot

```bash
cd /path/to/MaiBot/plugins/
# 将本目录（maibot-highrisk-blocker）复制到 plugins/ 下即可
```

### 2. 配置

编辑 `config.toml`（首次启动会自动生成，也可从 `config.example.toml` 复制）：

```toml
[plugin]
enabled = true
config_version = "1.0.0"

[blocker]
enabled = true
phrases = [
    "The request was rejected because it was considered high risk",
    "considered high risk",
]
```

### 3. 加载 / 重启 MaiBot

- 在 WebUI 插件管理页面对本插件执行「加载 / 重载」，或
- 重启 MaiBot，插件自动加载。

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `plugin.enabled` | 是否启用插件 | `true` |
| `blocker.enabled` | 是否启用高危消息拦截（为 `false` 时仅加载不拦截） | `true` |
| `blocker.phrases` | 命中即移除的文本片段列表（不区分大小写） | 见 `config.example.toml` |

## 拦截规则

- 消息文本（纯文本段）命中 `phrases` 中任意片段时，**移除该片段**；
- 若移除后仍有剩余正常内容 → 发送清理后的内容；
- 若移除后无剩余内容（整条消息就是错误原文）→ **中止发送**；
- 拦截只作用于 `type = "text"` 的消息段，图片等非文本段不受影响。

## 注意事项

- 拦截发生在**出站**阶段（`send_service.before_send` Hook），是所有发送消息的统一闸口；
- 建议定期查看日志中 `[highrisk-blocker]` 记录，若出现新的错误文案原文，补充到
  `blocker.phrases` 即可；
- 根本解决方案是检查 / 更换返回错误文案的 LLM 中转代理来源，本插件用于兜底防护。

## 许可

[MIT](LICENSE)
