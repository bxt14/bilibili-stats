# 🔘 毕导B站数据看板

自动采集毕导和毕的二阶导两个B站账号的视频数据，并生成可视化的数据看板网页。

## ✨ 功能特性

- 📊 **账号概览**：粉丝数、累计播放、累计获赞、作品数
- 📺 **视频时间线**：按发布时间展示所有视频，显示封面、标题、播放/点赞/投币
- 📈 **增长曲线**：点击视频查看5分钟级数据增长曲线（播放量、点赞、投币、收藏）
- 🌐 **GitHub Pages 部署**：生成静态HTML，一键部署到公网

## 🚀 快速开始

### 一键运行
```bash
bash run.sh
```

脚本会自动完成：
1. 采集B站账号和视频数据
2. 生成可视化HTML页面

### 部署到 GitHub Pages

1. 在 GitHub 创建一个仓库
2. 把 `bilibili-stats` 目录的内容推送到仓库
3. 仓库 → Settings → Pages → Source 选择 `docs` 文件夹
4. 访问你的网址：`https://你的用户名.github.io/仓库名/`

### 设置定时自动更新

编辑 crontab：
```bash
crontab -e
```

添加以下内容（每5分钟更新一次）：
```bash
*/5 * * * * cd /path/to/bilibili-stats && bash run.sh >> /var/log/bilibili-stats.log 2>&1
```

## 📁 项目结构

```
bilibili-stats/
├── scripts/
│   ├── fetch_data.py      # 数据采集脚本
│   └── generate_html.py   # HTML生成脚本
├── data/                   # 采集的JSON数据
│   ├── bidao_info.json
│   ├── bidao_videos.json
│   ├── erjiedao_info.json
│   ├── erjiedao_videos.json
│   └── growth_YYYY-MM-DD.json
├── docs/
│   └── index.html         # 最终网页
├── assets/                # 静态资源
├── run.sh                 # 一键运行脚本
└── README.md
```

## 🔧 配置说明

编辑 `scripts/fetch_data.py` 中的 `ACCOUNTS` 配置：
```python
ACCOUNTS = {
    'bidao': {
        'uid': '254463269',
        'name': '毕导',
        'recent_videos': ['BV1xxxxx', ...]  # 要追踪的视频BV号
    },
    ...
}
```

## 📊 数据采集说明

- **账号信息**：通过 B站公开API 获取
- **视频列表**：动态API获取 + 配置的BV号补充
- **增长数据**：每5分钟采集一次近30天发布的视频

## 🛠 技术栈

- **数据采集**：Python + Requests
- **可视化**：ECharts 5.4
- **部署**：GitHub Pages (纯静态HTML)

## 📝 注意事项

1. B站公开API有请求频率限制，不要过于频繁调用
2. 部分API可能需要登录Cookie才能正常工作
3. 增长曲线需要时间积累，连续运行几天后数据会更丰富

## 🎯 效果预览

- **首页**：两个账号卡片 + 时间线视频列表
- **详情页**：点击视频弹出详情，包含ECharts增长曲线，可切换播放/点赞/投币/收藏四个指标
