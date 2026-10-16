---
name: workbuddy-account-sync
description: 同一台机器上多个 WorkBuddy 账号之间对齐全部内容——工作空间（含中文名）、任务列表、任务进度、人格记忆；并支持把当前对话导出为 HANDOFF 供另一个账号接力。触发词：同步账号、账号对齐、换账号、切换 WorkBuddy 账号、导出对话、写 HANDOFF、接班、账号继承。
---

# WorkBuddy 多账号对齐

## 结论先行

本机切换 WorkBuddy 账号前跑一次、登录新账号后再跑一次，两个账号看到的内容就一致：工作空间、中文目录名、任务列表、任务进度全部对齐。

对话正文存在腾讯云端（按账号隔离，本地无缓存），**同步不了**——这部分靠 HANDOFF markdown 接力。

## 换账号标准流程

```
1) 【当前账号内】对 AI 说：导出本对话为 HANDOFF
   → 生成 <工作空间>/.workbuddy/HANDOFF-<任务>.md，AI 按模板填：
     背景目标 / 已完成 / 关键决策(含被否掉的) / 当前状态 / 产出文件 / 接手必读
   也可命令行生成空模板：
   python account_sync.py handoff --title "<任务>" --dir "<工作空间>"

2) 【退出 WorkBuddy】含托盘图标，必须完全退出

3) 【运行同步】
   python account_sync.py sync
   （Windows 双击 sync.cmd 亦可）

4) 【登录新账号】说：读取 <工作空间>/.workbuddy/HANDOFF-<任务>.md 接班
   再跑一次 python account_sync.py check 确认对齐
```

## 命令

| 命令 | 作用 | 是否需要退出 WorkBuddy |
|---|---|---|
| `check` | 只读体检：账号数、任务数、缺失副本、进度差异 | 否 |
| `sync` | 写库对齐（自动备份 DB） | **是**，未退出会拒绝 |
| `handoff` | 生成 HANDOFF 模板 | 否 |

常用参数：`--root <数据目录>`、`--from <账号前缀>`（指定基准账号）、`--pin <工作空间路径>`（置顶，可重复）、`--force`（跳过进程检查，不推荐）。

## sync 做了什么

| 步 | 动作 | 幂等 |
|---|---|---|
| 1 | 人格记忆 MEMORY/SOUL/IDENTITY/USER 以主账号为基准复制到所有账号 | ✅ |
| 2 | 规范化 `workspace-display-names.json` 分隔符（中文目录名才能显示） | ✅ |
| 3 | 任务列表**并集克隆**：每个账号补齐缺失任务（组键 cwd+created_at），复制 `tasks/<id>/` | ✅ 重复跑不产生副本 |
| 4 | **进度对齐**：同组副本取 `updated_at` 最新的为准，覆盖其余副本 | ✅ |
| 5 | `--pin` 的工作空间置顶 + 信任预置 | ✅ |

无 DELETE、无 DDL，每次先备份 `workbuddy.db.bak-<时间戳>`。

## 硬边界（别跟它较劲）

1. **对话正文同步不了**：消息只存腾讯云端，按"账号+会话 ID"拉取；克隆的是新会话 ID，云端无消息，点开显示"暂无对话记录"。本地无任何消息缓存（已全盘扫描取证），客户端无导出入口。→ 靠 HANDOFF。
2. **AI 读不到其他会话内容**：每个会话上下文独立，无法批量导出历史对话。只能打开一条导一条。
3. **别两个账号同时干同一条任务**：克隆副本会各自演化分叉，错峰用。

## 装到别的机器

```
git clone https://github.com/<owner>/workbuddy-account-sync
cp -r workbuddy-account-sync ~/.workbuddy/skills/workbuddy-account-sync   # 用户级技能目录
python ~/.workbuddy/skills/workbuddy-account-sync/account_sync.py check
```
Python 3.8+，无第三方依赖。
