# TLC-RAPID 使用说明

薄层色谱（TLC）斑点自动识别与浓度定量分析。

英文说明见 [README.md](README.md)。

## 快速开始（exe 版）

1. 双击 `TLC-RAPID.exe`，打开启动界面
2. 点击 **Open images folder**，放入 TLC 图片（`.jpg` / `.png`）
3. 点击 **Edit concentrations**，填写标准品浓度（从左到右）
4. 选择 **Imaging mode**（366 nm 荧光板选 `366nm`），点击 **Start Analysis**
5. 每张图检测完成后可**手动补标**漏检斑点（见下文）
6. 结束后在界面中打开结果目录（或查看 `runs/predict-seg/`）

> 纯命令行模式：`TLC-RAPID.exe --cli`

## 分析设置

**标准品浓度**（`user_input/standard_concentrations.csv`）：按斑点从左至右填写各标准品浓度；`(default)` 行为全局默认，也可按图片文件名单独设置。

标准品数量**不固定为 5**。软件以该表中有数值的 `standard_*` 列数为准：最左侧对应个数的斑点判为标准品，其右侧斑点判为待测样品。模板中的五列仅为示例；实际为 2、3、4、6 个或更多标准品时，增删 `standard_*` 列并填入相应浓度即可。

| image_filename | standard_1 | standard_2 | … | notes |
|----------------|------------|------------|---|-------|
| (default)      | 0.125      | 0.2        | … | 所有图片默认使用此行 |
| MyPlate.jpg    | …          | …          | … | 可为单张图单独设置 |

**可选参数**（`user_input/analysis_settings.csv`）：

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| imaging_mode | 366nm / visible / 254nm | 366 nm 荧光板建议设 366nm，勿依赖 auto（四边偏暗或非蓝边时可能误用 IOD） |
| quantification_method | isotonic | 日常分析；quadratic 复现论文 |
| confidence_threshold | 0.15 | 检测置信度 |

## 手动补标

| 操作 | 功能 |
|------|------|
| **左键点击** | **添加**框 |
| **右键点击** | **删除**框 |
| **S** | 保存并进入下一张 |
| **Esc** | 跳过补标，仅保留自动识别结果 |

请先点击**图片窗口**，再使用鼠标/键盘。按 **S** 后，所有斑点（含补标）按**从左至右**重新排序：最左侧若干个点为标准品（数量与 `standard_concentrations.csv` 标准列数一致），其余为样品。补标时请放准水平位置，以免标准品与样品归属错误。

结果标注图中：**绿框** = 标准品，**红框** = 样品，**黄框** = 手动补标（Excel 中 `Spot_Source = manual`）。部分环境下窗口可能无法弹出，程序会跳过补标并继续分析。

## 读取结果

每次分析结果保存在 `runs/predict-seg/exp*/`（或最新一次运行目录）下。样品定量结果在 **`quantitative_analysis_all_images.xlsx`** 中；**`Calculated_Concentration`** 列即为各待测斑点的预测浓度，单位与 `standard_concentrations.csv` 中所填标准品浓度一致。若 **`Out_of_Range`** 为 `True`，表示该点响应或反算浓度超出标准曲线验证范围，所给数值仅供参考。

| 列名 | 含义 |
|------|------|
| `Image` | 图片文件名 |
| `Spot_Index` | 斑点序号（从左至右） |
| `Spot_Type` | `standard`：标准品；`sample`：待测样品 |
| `Known_Concentration` | 标准品已知浓度 |
| **`Calculated_Concentration`** | **待测样品预测浓度** |
| `Out_of_Range` | 是否超出标准曲线验证范围 |
| `Range_Status` | 超范围判定说明 |
| `Calibration_Y_Axis` | 校准所用响应指标（IGI / peak_1d / IOD） |
| `Response_Axis_Source` | 366 nm 响应轴来源（`igi` 或 `peak_1d_fallback`） |

## 源码与许可

本软件源码以 **GNU Affero General Public License v3.0（AGPL-3.0）** 公开发布，详见 [LICENSE](LICENSE) 与英文说明 [README.md](README.md)。

- 源码仓库：`https://github.com/<YOUR_USERNAME>/TLC-RAPID`（上线后请替换为真实公开地址）
- 可向用户分发 Windows 可执行文件（`TLC-RAPID.exe`），但须同时提供上述仓库链接，以便获取对应源码（AGPL-3.0 要求）

