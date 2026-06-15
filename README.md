# astrbot_plugin_poke_pro

专业戳一戳插件，支持主动戳人和自动戳人。

## 功能

| 功能 | 说明 |
|------|------|
| 🔨 主动戳人 | `/poke chuo @某人` 或 `/poke chuo QQ号` |
| 📊 状态查看 | `/poke status` 查看插件运行状态 |
| ⏰ 自动戳人 | 配置开启后可定时自动戳人 |

## 安装

将 `astrbot_plugin_poke_pro` 目录放入 AstrBot 的 `data/plugins/` 目录下。

## 指令说明

### 主动戳人

```
/poke chuo @某人
/poke chuo 123456789
```

- 在群聊中使用时，支持 `@某人` 方式指定目标
- 也可以直接输入目标 QQ 号
- 私聊中自动使用 `friend_poke`

### 查看状态

```
/poke status
```

显示插件启用状态、自动戳人配置、QQ 连接状态等。

## 配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable` | bool | true | 是否启用插件 |
| `auto_poke_enable` | bool | false | 是否启用自动戳人 |
| `auto_poke_interval` | int | 60 | 自动戳人间隔（秒），范围 10-3600 |

## 依赖

- AstrBot 框架
- OneBot v11 适配器（NapCat / LLOneBot / Lagrange 等）
- 需要 OneBot 实现支持 `group_poke` 和 `friend_poke` 扩展 API

## 作者

bentianjia

## 版本

v1.0.0
