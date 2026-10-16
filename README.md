# workbuddy-account-sync

Same machine, multiple WorkBuddy accounts — make them all see the same thing.

同一台机器上多个 WorkBuddy 账号之间，把**工作空间（含中文目录名）、任务列表、任务进度、人格记忆**全部对齐；对话正文因存在云端无法同步，改用 **HANDOFF markdown** 接力。

Python 3.8+，零第三方依赖。

---

## Why / 为什么

WorkBuddy 把账号相关的数据分成三层，只有中间那层能在本机对齐：

| 层 | 例子 | 跨账号 |
|---|---|---|
| 本机共享 | 技能、工作空间文件、项目记忆、API 凭据 | ✅ 本来就有 |
| 本机但按账号隔离 | `workbuddy.db` 的 sessions、人格文件 MEMORY/SOUL、workspace 显示名 | ✅ **本工具可对齐** |
| 云端按账号隔离 | **对话正文**、云端画像、资料库、连接器授权 | ❌ 无解，靠 HANDOFF |

对话正文：消息只存在云端，按「账号 + 会话 ID」拉取，本地无缓存、客户端无导出入口。克隆出的任务是新会话 ID，云端没有对应消息，点开就是「暂无对话记录」。这点别再想办法了。

## Usage / 用法

### 换账号的标准流程

```bash
# 1) 当前账号内：把对话结论导成 HANDOFF（让 AI 按模板填）
python account_sync.py handoff --title "任务名" --dir "<工作空间>"

# 2) 完全退出 WorkBuddy（含托盘图标）

# 3) 对齐
python account_sync.py sync

# 4) 登录另一个账号，读 HANDOFF 接班；可再跑一次确认
python account_sync.py check
```

### 命令

| 命令 | 作用 | 需退出 WorkBuddy |
|---|---|---|
| `check` | 只读体检：账号数 / 任务数 / 缺失副本 / 进度差异 | 否 |
| `sync` | 写库对齐（先自动备份 `workbuddy.db`） | **是**，未退出直接拒绝 |
| `handoff` | 生成 HANDOFF 模板 | 否 |

参数：`--root <数据目录>`（默认自动探测 `$WORKBUDDY_CONFIG_DIR` 或 `~/.workbuddy`）、`--from <账号前缀>`、`--pin <工作空间>`（置顶，可重复）、`--force`（跳过进程检查）。

### sync 五步

1. 人格记忆以主账号（任务最多的那个）为基准复制到所有账号
2. 规范化 `workspace-display-names.json` 的分隔符 —— 中文目录名能不能显示就看它
3. 任务列表**并集克隆**：每个账号补齐缺失任务（组键 `cwd + created_at`），复制 `tasks/<id>/`
4. **进度对齐**：同组副本取 `updated_at` 最新的为准，覆盖其余副本
5. `--pin` 的空间置顶 + 信任预置

全部幂等，重复跑不产生副本。无 DELETE、无 DDL，每次自动备份数据库。

## Install / 安装

```bash
git clone https://github.com/t42h74ftzj-maker/workbuddy-account-sync
cp -r workbuddy-account-sync ~/.workbuddy/skills/workbuddy-account-sync
```
装进用户级技能目录后，在 WorkBuddy 对话里直接说「同步账号」「导出本对话为 HANDOFF」即可触发。

## 边界

- **两个账号别同时干同一条任务** —— 克隆副本会各自演化分叉，错峰用。
- **AI 读不到其他会话内容**（上下文独立），所以无法批量导出历史对话，只能打开一条导一条。
- 导结论，不导聊天记录。HANDOFF 要的是「决定了什么、做到哪、下一步」。

## License

MIT
