---
name: workbuddy-account-sync
description: 同一台机器上多个 WorkBuddy 账号之间对齐全部内容——工作空间（含中文名）、任务列表、任务进度、人格记忆；并支持把当前对话导出为 HANDOFF 供另一个账号接力。触发词：同步账号、账号对齐、换账号、切换 WorkBuddy 账号、导出对话、写 HANDOFF、接班、账号继承。
---

# WorkBuddy 多账号对齐

## 结论先行

本机切换 WorkBuddy 账号前跑一次、登录新账号后再跑一次，两个账号看到的内容就一致：工作空间、中文目录名、任务列表、任务进度全部对齐。

对话正文存在腾讯云端（按账号隔离，本地无缓存），**同步不了**——这部分靠 HANDOFF markdown 接力。

## 换账号：两条命令搞定（中间必须退出应用，这是硬边界）

```
A) 还在当前账号 → 一条命令：
   python account_sync.py prepare
   · 体检（账号数/任务数/差异）
   · 为最近活跃的任务批量生成 HANDOFF 骨架，元数据自动填好
     （工作空间、状态、最后活动、最近产出文件），AI 只需补结论

   然后对 AI 说一句：填写这些 HANDOFF 文件
   ↑ 这一步 AI 补"结论 / 决策 / 下一步"，是唯一必须人工参与的环节

B) 退出 WorkBuddy → 一条命令：
   python account_sync.py sync      （Windows 双击 sync.cmd）
   · 人格记忆 / 中文目录名 / 任务列表并集克隆 / 进度对齐 / 空间置顶
   · 顺手在每个工作空间写 RESUME.md（接班索引）

C) 登录另一个账号 → 一条命令（或直接让 AI 说"接班"）：
   python account_sync.py resume
   · 列出所有 HANDOFF， newest first，告诉你读哪个
```

**为什么不能一条命令跑完 4 步**：第 A 步必须在账号内（AI 要读上下文），第 B 步必须在退出后（要写数据库），中间隔着重启应用，任何脚本都跨不过去。已经压到 **2 条命令 + 1 句 AI 指令**，这是物理下限。

## 命令

| 命令 | 作用 | 是否需要退出 WorkBuddy |
|---|---|---|
| `prepare` | 体检 + 批量生成 HANDOFF 骨架（元数据自动填） | 否 |
| `sync` | 写库对齐 + 写 RESUME.md 接班索引（自动备份 DB） | **是**，未退出会拒绝 |
| `resume` | 列出可接手的 HANDOFF，告诉你读哪个 | 否 |
| `check` | 只读体检：账号数、任务数、缺失副本、进度差异 | 否 |
| `handoff` | 单独生成一份 HANDOFF 模板 | 否 |

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
git clone https://github.com/t42h74ftzj-maker/workbuddy-account-sync
cp -r workbuddy-account-sync ~/.workbuddy/skills/workbuddy-account-sync   # 用户级技能目录
python ~/.workbuddy/skills/workbuddy-account-sync/account_sync.py check
```
Python 3.8+，无第三方依赖。
