布卡漫画下载文件提取工具
====================
从布卡下载文件中抽取出漫画图片，并自动重命名其文件夹。

## 功能
支持提取布卡漫画现有的多种格式（包括.buka，.jpg.view，.bup.view），保存为普通图片，并自动对文件夹重命名为漫画名和卷名。

## 用法
请先将安卓手机中的漫画文件夹（/sdcard/ibuka/down）复制到硬盘再操作。

请先下载 `buka.py` ， `dwebp.exe` (Windows) 或 `dwebp` (Linux)。注意：在Linux下必须给 `dwebp` 赋予执行权限！

    chmod +x dwebp

切换到程序所在的文件夹，命令行：（可省略输出路径，默认为与输入文件夹同目录下的output）

    python3 buka.py INPUT_DIR_or_BUKA_FILE [OUTPUT_DIR]

然后就可以使用各种图片浏览器、漫画阅读器欣赏漫画。

### 原版
作者对.buka解析的源文件保留在此。运行 `buka.py` 时无需原版。

    python2 refbuka.py INPUT_DIR OUTPUT_DIR
