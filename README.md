# blender-

本仓库用于 **Blender 插件的测试与应用**。

## 用途

- 开发、测试和验证 Blender 插件
- 存放插件源码、测试脚本与使用文档
- 作为个人 Blender 工具链的实验环境

## 环境

- Blender 3.x / 4.x（推荐最新稳定版）
- Python 3.14.4（本地开发，清华镜像源）
- Git + SSH（GitHub 认证）

## 目录结构

```
blender-
├── addons/          # 插件源码（安装到 Blender 后位于 addons 目录）
├── tests/           # 插件测试脚本
├── docs/            # 使用文档
└── README.md
```

## 快速开始

1. 将 `addons/` 下的插件目录复制到 Blender 的 `addons` 目录：
   - Windows: `%APPDATA%\Blender Foundation\Blender\<版本>\scripts\addons\`
2. 在 Blender 中：`Edit > Preferences > Add-ons` 启用对应插件
3. 插件测试脚本位于 `tests/`，可在 Blender 的 Scripting 工作区运行

## 许可

保留权利（私有仓库）。
