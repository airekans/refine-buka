布卡漫画下载文件提取工具
========================
从布卡下载文件中抽取出漫画图片，并自动重命名其文件夹。

_Scroll down for English documentation._

## 功能
支持提取布卡漫画现有的多种格式（包括.buka，.jpg.view，.bup.view），保存为普通图片，并自动对文件夹重命名为漫画名和卷名。

## 版本历史
### 2.5 版本
* 修正重命名问题，提示最终输出文件夹
* 无转换中间过程 WebP 结果输出，加快速度
* 限制队列数目，避免内存占用过大
* 增加仅探测文件/文件夹功能 --info
* 增加删除非图像文件选项 --clean

### 2.4 版本
* 支持包装了 JPG 的新 .bup 文件
* 加入 -n, --keepwebp 选项保留 WebP 文件
* 加入 -q, --quality 选项指定 JPG 质量
* 无转换中间过程 PNG 结果输出
* 日志输出漫画名
* 修复重命名问题
* API 更新
* 升级解码器

### 2.3 版本
* 优化错误处理、稳定性
* 默认启用 Pillow 来转换 PNG 到 JPG

### 2.2 版本
* 优化 Windows 下用户体验。默认输出位置改为与输入文件夹**相同**目录，而不是“当前文件夹”。

### 2.1 版本
* 修正几个重命名问题，dwebp 解码优先。

### 2.0 版本
* 将各类文件格式用对象表示，可访问属性及操作。
  * `BukaFile` 对 .buka 文件的解析与提取
  * `ComicInfo` 对 chaporder.dat 文件的解析
* `buildfromdb` 解析iOS平台下数据库 buka_store.sql，并实现其对 chaporder.dat 的转换。
* `DirMan` 实现自动重命名
* `DwebpMan` 实现 dwebp 进程池
* `DwebpPILMan` 实现 PIL 解码器线程池
* 重写重命名部分，实现规范化的命名逻辑。
* 日志模块，简化错误报告
* ……

可通过 `import buka` 来进行研究和扩展功能。

如果有 Pillow (PIL) 模块，加 `--pil` 参数可更快速地解码。

**注意：**请使用[最新版本](https://github.com/python-pillow/Pillow)的 Pillow，内存泄漏问题已在最新版中解决。

## 用法

必须使用 Python 3 运行程序。

**Windows 发行版**：直接将待转换文件/文件夹拖入软件图标即可，**不要**直接双击运行。在命令行环境将以下所有 `[python3] buka.py` 替换为 `buka.exe`。

```
用法: buka.py [-h] [-i] [-e] [-p NUM] [-c] [-l] [-n] [--pil] [--dwebp DWEBP]
               [-q NUM] [-d buka_store.sql]
               input [output]

转换布卡漫画下载的漫画文件。

固定参数:
  input                 .buka 文件或包含下载文件的文件夹
                        通常位于 (安卓SD卡) /sdcard/ibuka/down
  output                指定输出文件夹 (默认 = ./output)

可选参数:
  -h, --help            显示帮助信息并退出
  -i, --info            仅显示指定文件 (夹) 信息
  -e, --clean           删除非图像文件
  -p NUM, --process NUM
                        dwebp 的最大进程数 / PIL 解码的最大线程数
                        (默认 = CPU 核心数)
  -c, --current-dir     默认输出文件夹改为 <当前目录>/output.
                        当指定 <output> 时忽略
  -l, --log             强制保存错误日志
  -n, --keepwebp        保留 WebP 格式图片，不转换
  --pil                 PIL/Pillow 解码优先，速度更快，但可能导致
                        内存泄漏。(Windows 编译发行版本不可用)
  --dwebp DWEBP         指定 dwebp 解码器位置
  -q NUM, --quality NUM
                        JPG 质量 (默认 = 92)
  -d buka_store.sql, --db buka_store.sql
                        指定 iOS 设备中 buka_store.sql 文件位置
                        此文件提供了额外的重命名信息
```

可省略输出路径，默认为与输入文件夹同目录的output，加-c为当前目录下的output。
此output文件夹可能被重命名为适当的符合输入文件(夹)的名称。

然后就可以使用各种图片浏览器、漫画阅读器欣赏漫画。

## 问题
请使用最新版 Pillow，否则在解码 WebP 时有内存泄漏问题。

## 授权

MIT 协议

--------------------

Buka Comics file extractor
===========================

Extracts downloaded files and folders by Buka, and automatically renames the folders.

## Function
Support various formats of Buka (including .buka, .jpg.view, .bup.view). It saves results to common image format and renames the folders according to the comic name or chapter name.

## 2.x Version
You can `import buka` to extend its functions.

If the latest Pillow library is installed, use `--pil` for faster decoding.

**Note** that the [latest version](https://github.com/python-pillow/Pillow) of Pillow has fixed the memory leak of the WebP decoder. Please use `--pil` to enable it.

## Usage

Python 3 only.

**Windows Release**: Drag and drop the file or folder onto the icon. *Don't* directly double-click run. Replace all `[python3] buka.py` commands below with `buka.exe`.

python3 buka.py -h
```
usage: buka.py [-h] [-i] [-e] [-p NUM] [-c] [-l] [-n] [--pil] [--dwebp DWEBP]
               [-q NUM] [-d buka_store.sql]
               input [output]

Converts comics downloaded by Buka.

positional arguments:
  input                 The .buka file or the folder containing files
                        downloaded by Buka, which is usually located in
                        (Android) /sdcard/ibuka/down
  output                The output folder. (Default = ./output)

optional arguments:
  -h, --help            show this help message and exit
  -i, --info            Only show file/folder information.
  -e, --clean           Delete non-image files.
  -p NUM, --process NUM
                        The max number of running dwebp's. (Default = CPU
                        count)
  -c, --current-dir     Change the default output dir to ./output. Ignored
                        when specifies <output>
  -l, --log             Force logging to file.
  -n, --keepwebp        Keep WebP, don't convert them.
  --pil                 Perfer PIL/Pillow for decoding, faster, and may cause
                        memory leaks.
  --dwebp DWEBP         Locate your own dwebp WebP decoder.
  -q NUM, --quality NUM
                        JPG quality. (Default = 92)
  -d buka_store.sql, --db buka_store.sql
                        Locate the 'buka_store.sql' file in iOS devices, which
                        provides infomation for renaming.
```

Output path can be omitted. The default output folder is `output` folder under the same directory as the input file. Use -c to change to current working directory.

This `output` directory may be renamed to a more suitable name.

After several minutes, you can use your favorate image viewer to enjoy the comics.

## Known Issues
Workaround methods are used to solve the memory leak problem of the (previous or stable version) Pillow WebP decoder.

## License
The MIT License

