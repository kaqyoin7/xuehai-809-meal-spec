---
# 复制本文件为 entries/NNNN.md，或运行：python build.py new "店名"
# 以 _ 开头的文件不会被收录。
# 只有 name 和（线下店的）where 是希望保留的，其余的行都可以删掉。
# 一旦使用，编号 no 就不再复用，店关了也保留（把 status 改成 retired）。
no: 0
name: 店名
type: 堂食          # 堂食 / 外卖 / 都可以
where:              # 线下店写位置，外卖写平台
by:                 # 推荐人（可选）
date:               # 年-月-日（可选）
figure:             # 图片文件名，放在 figures/ 下（可选）
figure_caption:     # 图注（可选）
figure_width: 8cm
status: active      # active / retired
retired_note:       # 停止推荐时写：日期，原因
---
下面每一行会成为卡片里的一行，写法不限，例如：
人均 15 元
推荐：……　　不推荐：……
点评：……
适合：一个人吃
