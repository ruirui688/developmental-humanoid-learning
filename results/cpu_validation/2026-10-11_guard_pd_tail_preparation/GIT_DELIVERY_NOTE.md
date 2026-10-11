# 准备原件的 Git 交付补充

首次提交 `0c51c71` 的普通 add 没有收录10个包含嵌套 external/ 的来源快照：它们命中了仓库的外部目录忽略规则。原封口清单及本地原件均未改变。随后一次定向 add 还遇到了 Windows Git 的长路径限制，没有成功修改 index。

只增加本归档目录内嵌套 external/ 的精确忽略例外，并用 `git -c core.longpaths=true add` 提交遗漏原件。保留先前提交；没有重跑复制、数学、模型或物理。Windows 检出这些原始嵌套路径时也需要启用 Git 长路径支持。该补充不是85个原封口payload之一，原manifest保持原字节。
