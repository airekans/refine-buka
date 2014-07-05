布卡漫画下载文件提取工具
====================
从布卡下载文件中抽取出漫画图片，并自动重命名其文件夹。

## 2.0 版本
* 将各类文件格式用对象表示，可访问属性及操作。
* `buildfromdb` 解析iOS平台下数据库buka_store.sql，并实现其对chaporder.dat的转换。
* 重写重命名部分，实现规范化的命名逻辑。
* `BukaFile` 对.buka文件的解析与提取
* `ComicInfo` 对chaporder.dat文件的解析
* `DirMan` 实现自动重命名
* `DwebpMan` 实现 dwebp 进程池
* `DwebpPILMan` 实现 PIL 解码器线程池
* 日志模块，简化bug报告
* ……

可通过 `import buka` 来进行研究和扩展功能。

如果有 Pillow (PIL) 模块并支持 WebP，可直接解码成 png。


## 功能
支持提取布卡漫画现有的多种格式（包括.buka，.jpg.view，.bup.view），保存为普通图片，并自动对文件夹重命名为漫画名和卷名。

## 用法

必须使用 Python 3 运行程序。

```
用法: buka.py [-h] [-p NUM] [-s] [--dwebp [DWEBP]] [-d buka_store.sql]
               input [output]

转换布卡漫画下载的漫画文件。

固定参数:
  input                 .buka 文件或包含下载文件的文件夹
                        通常位于 (安卓SD卡) /sdcard/ibuka/down
  output                指定输出文件夹 (默认 = ./output)

可选参数:
  -h, --help            显示帮助信息并退出
  -p NUM, --process NUM
                        dwebp 的最大进程数 / PIL 解码的最大线程数
                        (默认 = CPU 核心数)
  -s, --same-dir        默认输出文件夹改为 <input>/../output.
                        当指定 <output> 时忽略
  --dwebp [DWEBP]       dwebp 解码优先，并指定 dwebp 解码器位置
  -d buka_store.sql, --db buka_store.sql
                        指定 iOS 设备中 buka_store.sql 文件位置
                        此文件提供了额外的重命名信息
```

python3 buka.py -h
```
usage: buka.py [-h] [-p NUM] [-s] [--dwebp [DWEBP]] [-d buka_store.sql]
               input [output]

Converts comics downloaded by Buka.

positional arguments:
  input                 The .buka file or the folder containing files
                        downloaded by Buka, which is usually located in
                        (Android) /sdcard/ibuka/down
  output                The output folder. (Default = ./output)

optional arguments:
  -h, --help            show this help message and exit
  -p NUM, --process NUM
                        The max number of running dwebp's. (Default = CPU
                        count)
  -s, --same-dir        Change the default output dir to <input>/../output.
                        Ignored when specifies <output>
  --dwebp [DWEBP]       Perfer dwebp for decoding, and/or locate your own
                        dwebp WebP decoder.
  -d buka_store.sql, --db buka_store.sql
                        Locate the 'buka_store.sql' file in iOS devices, which
                        provides infomation for renaming.
```

（可省略输出路径，默认为当前目录下的output，加-s为与输入文件夹同目录下的output）

然后就可以使用各种图片浏览器、漫画阅读器欣赏漫画。

## 问题
因为采用了 no WIC 版本的 dwebp.exe，对 Windows SP2 及以下操作系统已兼容。

如果采用外部程序 dwebp 解码，由于仅将 .bup/webp 格式直接转换成 png 格式，所以文件大小偏大。用户可自行转换成 jpg 以减小文件体积( `python3 png2jpg.py 目录` )。
