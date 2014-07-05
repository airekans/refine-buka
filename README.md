布卡漫画下载文件提取工具
====================
从布卡下载文件中抽取出漫画图片，并自动重命名其文件夹。

## 2.0 版本
* 将各类文件格式用对象表示，可访问属性及操作。
* 解析iOS平台下数据库buka_store.sql，并实现其对chaporder.dat的转换。
* 重写重命名部分，实现规范化的命名逻辑。

* `BukaFile` 对.buka文件的解析与提取
* `ComicInfo` 对chaporder.dat文件的解析
* `DirMan` 实现自动重命名
* `DwebpMan` 实现 dwebp 进程/线程池

可通过`import buka`来进行研究和扩展功能。

如果有 Pillow 模块，可直接解码成 png。


## 功能
支持提取布卡漫画现有的多种格式（包括.buka，.jpg.view，.bup.view），保存为普通图片，并自动对文件夹重命名为漫画名和卷名。

## 用法
请先将安卓手机中的漫画文件夹（/sdcard/ibuka/down）复制到硬盘再操作。

请先下载 `buka.py` ， `dwebp.exe` (Windows) 或 `dwebp` (Linux)。注意：在Linux下必须给 `dwebp` 赋予执行权限！

    chmod +x dwebp

切换到程序所在的文件夹，命令行：（可省略输出路径，默认为与输入文件夹同目录下的output）

    python3 buka.py INPUT_DIR_or_BUKA_FILE [OUTPUT_DIR]

然后就可以使用各种图片浏览器、漫画阅读器欣赏漫画。

## 问题
因为采用了 no WIC 版本的 dwebp.exe，对 Windows SP2 及以下操作系统已兼容。

如果采用外部程序 dwebp 解码，由于仅将 .bup/webp 格式直接转换成 png 格式，所以文件大小偏大。用户可自行转换成 jpg 以减小文件体积（png2jpg.py）。
