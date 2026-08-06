# blender-

本仓库用于 **Blender 插件的测试与应用**。

## 用途

- 开发、测试和验证 Blender 插件
- 存放插件源码、测试脚本与使用文档
- 作为个人 Blender 工具链的实验环境

## 环境

- Blender 5.2.0 LTS（Steam 安装，`D:\SteamLibrary\steamapps\common\Blender`）
- Python 3.14.4（本地开发，清华镜像源）
- Git + SSH（GitHub 认证）

## 目录结构

```
blender-
├── addons/          # 插件源码
│   └── curve_mesh_generator.py
├── tests/           # 插件测试脚本（Blender headless 运行）
├── docs/            # 使用文档
└── README.md
```

## 插件：Curve Mesh Generator

根据现有曲线一键生成 **管道 (Pipe)**、**梯子 (Ladder)**、**栏杆 (Railing)** 三种网格物体。

### 功能

| 功能 | 说明 |
| --- | --- |
| 管道 | 沿曲线生成中空圆柱，可调半径、环面数（圆周分段）、纵向分段 |
| 梯子 | 沿曲线方向生成两侧纵梁 + 横档，可调宽度、横档数量、横档圆周面数 |
| 栏杆 | 沿曲线生成上/下横杆 + 立柱，可调高度、立柱数量、杆件直径 |
| 分段/面数编辑 | 生成物体会绑定其来源曲线；选中物体后可加载参数并基于原曲线重建 |
| 倒角 | 为生成物体添加/更新 Bevel 修改器（宽度、分段数可调，非破坏性） |

### 安装

1. 将 `addons/curve_mesh_generator.py` 复制到 Blender 的 addons 目录：
   - `%APPDATA%\Blender Foundation\Blender\5.2\scripts\addons\`
   - 或 `Edit > Preferences > Add-ons > Install` 选择该文件
2. 搜索并启用 **Curve Mesh Generator**

### 使用方法

1. 在 3D 视图中创建/选中一条曲线（Poly 或 Bezier 均可）
2. 右侧 **N 面板 > Curve Mesh** 选项卡
3. 选择生成类型（Pipe / Ladder / Railing）并设置参数
4. 点击 **Generate** 生成网格物体
5. 选中已生成的物体 → 面板自动加载其参数 → 修改分段/面数/倒角 → 点击 **Update Selected** 重建

### 测试

```powershell
& "D:\SteamLibrary\steamapps\common\Blender\blender.exe" --background --factory-startup `
  --python "E:\blender-\tests\test_curve_mesh_generator.py"
```

测试脚本在 Blender headless 模式下验证：插件启用、三种物体生成（顶点/面数精确断言）、参数更新、倒角修改。

## 许可

本项目采用 **GNU Lesser General Public License v3.0 (LGPL-3.0)**。

详见 [LICENSE](LICENSE)（许可证正文另见 [COPYING.LESSER](COPYING.LESSER)）。
