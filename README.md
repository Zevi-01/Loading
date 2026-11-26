# LN 入仓排车优化 🚛

**核心目标**：给定若干 LN 号及其卡板数，在不拆分 LN 的前提下，选择车型组合使总费用 Q 最低。

- ✅ **严格全局最优**：穷举所有合理车型数量组合 + 回溯搜索保证可行装配
- ✅ **卡板约束**：每种车型有卡板上限
- ✅ **不拆分 LN**：同号 LN 必须完整装到一辆车上
- ✅ **Q 值最低**：枚举时按 Q 升序，找到第一个可行解就是最优

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 准备 Excel

三列即可（列名可改，见 `run.py` 底部参数）：

| LN号 | 卡板数 | 体积（可选） |
|------|--------|-------------|
| LN-A001 | 20 | 60 |
| LN-A002 | 18 | 55 |

### 3. 命令行运行

```bash
python run.py LN数据.xlsx 排车结果.xlsx
```

### 4. Web 界面运行

```bash
streamlit run web/app.py
```

浏览器打开显示的本地地址 → 上传 Excel → 点运行 → 下载结果。

## 项目结构

```
.
├── src/
│   ├── __init__.py
│   ├── config.py       # 车型配置（改这里加新车型/改Q值）
│   ├── models.py       # 数据类（LN / VehiclePlan / PlanResult）
│   ├── data_loader.py  # Excel 读取
│   ├── solver.py       # 核心算法（车型组合枚举 + 回溯搜索）
│   └── exporter.py     # Excel 输出
├── web/
│   └── app.py          # Streamlit Web 界面
├── run.py              # 命令行入口
├── requirements.txt
└── README.md
```

## 车型配置

编辑 `src/config.py`：

```python
VEHICLE_TYPES = [
    ("7.6M",  12,  8300),   # (车型名, 卡板上限, Q值)
    ("9.6M",  16,  9800),
    ("40HQ",  21, 12000),
    ("45HQ",  23, 12500),
    ("17.5M", 34, 16600),
]
```

## 输出

Excel 三个 Sheet：
- **成本汇总**：派车总数、总 Q、各车型分布
- **派车明细**：每辆车装了哪些 LN、卡板利用率
- **异常警告**：卡板>34 的 LN（无法装下，需人工处理）

## 算法说明

1. **车型组合枚举**：遍历所有可能的车辆数 k（理论最少 ~ 理论最多），枚举 5 种车型在 k 辆车中的数量分配
2. **按 Q 升序排列**：Q 最低的组合最先尝试，一旦找到可行装配就是全局最优
3. **内层装配**：先贪心 Best Fit 快速试装，失败再走回溯搜索 + 剪枝（保证找到可行解，如果存在）
4. **保底贪心**：枚举超时或找不到时，退化为贪心 + Merge + Resize 后处理

## 注意事项

- 超过 `MAX_PAL=34` 板的 LN 无法装下，会在结果中警告
- 枚举默认 30 秒超时，超时后退化为贪心
- 20~30 条 LN 秒级出结果；超过 30 条建议分批处理

## Git 部署

```bash
# 1. 安装 Git（如果没装）：https://git-scm.com/download/win

# 2. 初始化仓库
git init
git config user.email "your_email@example.com"
git config user.name "Your Name"

# 3. 提交
git add .
git commit -m "feat: LN入仓排车优化 · 车型组合枚举全局最优"

# 4. 推送到 GitHub / GitLab
git branch -M main
git remote add origin https://github.com/你的用户名/仓库名.git
git push -u origin main

# 5. 他人 clone 后运行
git clone https://github.com/你的用户名/仓库名.git
cd 仓库名
pip install -r requirements.txt
python run.py
# 或 Web：streamlit run web/app.py
```

### Streamlit Cloud 免费部署

1. GitHub 上新建仓库，push 代码
2. https://share.streamlit.io → New app → 选 GitHub 仓库
3. Branch = `main`, Main file path = `web/app.py`
4. 点 Deploy → 几分钟后获得线上 URL，上传 Excel 就能用
