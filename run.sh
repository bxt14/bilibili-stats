#!/bin/bash
# B站数据看板一键运行脚本

cd "$(dirname "$0")"

echo "🔘 毕导B站数据看板"
echo "===================="

# 1. 采集数据
echo ""
echo "📥 正在采集数据..."
python3 scripts/fetch_data.py

# 2. 生成HTML
echo ""
echo "🌐 正在生成网页..."
python3 scripts/generate_html.py

echo ""
echo "✅ 完成！"
echo ""
echo "📁 数据文件: data/"
echo "🌐 网页文件: docs/index.html"
echo ""
echo "部署到 GitHub Pages 步骤："
echo "  1. 在 GitHub 创建仓库"
echo "  2. 把 bilibili-stats 目录推送到仓库"
echo "  3. 仓库设置 → Pages → 源选择 docs 文件夹"
echo "  4. 访问: https://你的用户名.github.io/仓库名/"
echo ""
echo "设置定时自动更新："
echo "  crontab -e"
echo "  添加: */5 * * * * cd /path/to/bilibili-stats && bash run.sh"
echo "  (每5分钟更新一次数据)"
