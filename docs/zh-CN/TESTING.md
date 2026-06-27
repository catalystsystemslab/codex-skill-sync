# Skill Sync Beta 测试

这个清单给正在公开 Beta 阶段试用 Skill Sync 的用户使用。

## 初学者测试流程

问 Codex：

```text
/skill-sync doctor
```

然后：

```text
/skill-sync check
```

只有在你看懂输出之后，再尝试：

```text
/skill-sync update
```

## 需要检查什么

- `doctor` 不会做任何修改。
- `check` 不会做任何修改。
- 技能会被分为 Official、Community 或 Needs Setup。
- 未知来源的技能会被跳过。
- 本地或私有技能不会被覆盖。
- 应用更新前需要确认。
- 替换前会创建备份。
- 失败的安全检查能看懂。
- 在 Codex 之外使用时，Codex 插件警告不会让人困惑。

## 建议的 Beta 场景

尝试这些组合：

- 一个已知的公开技能
- 一个私有或本地技能
- 一个没有已知来源的技能
- 一个有效的 manifest 条目
- 一个故意写错的 manifest 条目，如果你愿意测试失败输出

## 高级直接 CLI 检查

在仓库根目录运行：

```bash
python3 skill-sync/scripts/update_codex_assets.py --doctor
python3 skill-sync/scripts/update_codex_assets.py --doctor --json
python3 skill-sync/scripts/update_codex_assets.py --inventory --no-plugins
python3 skill-sync/scripts/update_codex_assets.py --json --no-plugins
```

运行内置检查：

```bash
python3 skill-sync/scripts/update_codex_assets.py --self-test
python3 -m compileall skill-sync/scripts/update_codex_assets.py
git diff --check
```

## 反馈什么

请报告：

- 安装是否卡住
- 输出是否难懂
- 映射来源是否困惑
- 是否有任何行为让你在更新前犹豫
- 备份或恢复说明是否不清楚
- 是否出现 Python traceback
- 是否有 Skill Sync 看起来猜得太多的情况

请使用 `.github/ISSUE_TEMPLATE/` 中的 issue 模板。
