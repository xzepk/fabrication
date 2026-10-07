# Windows / Linux Operations

## Python

推荐 Python 3.11–3.13，使用独立虚拟环境。

```bash
pip install -e .
```

## Windows

- Python 64-bit
- .NET 8 SDK（只有直接 DWG ACadSharp helper 需要）
- 构建 `native/acadsharp-dump`
- 设置 `CADFAB_ACADSHARP_DUMP`

## Linux

- Python 64-bit
- glibc 较新的主流发行版
- .NET 8 SDK/runtime（直接 DWG helper 需要）
- CadQuery/OCP wheel 必须与 Python/架构匹配

## 恢复

项目运行数据永远写在 `<project>`，不写 Skill 自身目录。每次 run 都创建独立 run-id，不覆盖旧产物。输入或 config 变化后重新 `snapshot`；旧确认不会自动迁移到新快照。

## Provider 切换

修改项目 `config/project.yaml` 后重新 snapshot。生产过程中禁止“OCCT 失败就自动切 Rhino”或反向静默回退。
