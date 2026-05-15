# 德语学习复习网站

这是一个用 Python + Flask + SQLite 做的本地学习网站。

## 已有功能

1. 单词管理：添加德语、中文、例句，也可以删除单词
2. 间隔复习：记住后下次复习时间会变长，忘记后从明天重新开始
3. 阅读错题记录：保存阅读题、原文线索和错因
4. 听力错题记录：保存听错内容和错因
5. 写作模板库：保存写作句型、开头、结尾、连接词
6. 今日复习页面：只显示今天需要复习的单词
7. 手机浏览器适配：页面优先适配手机屏幕，按钮更大，方便点击
8. CSV 导入和批量粘贴导入单词
9. PWA 预备结构：已生成 manifest，并预留 service worker 离线缓存结构

## 第一步：进入项目文件夹

打开 PowerShell，输入：

```powershell
cd "C:\Users\lenovo\Documents\单运来"
```

## 第二步：安装需要的工具

如果之前已经安装过，可以跳过这一步。

```powershell
python -m pip install -r requirements.txt
```

## 第三步：启动网站

```powershell
python app.py
```

看到类似下面的提示就说明启动成功：

```text
Running on http://127.0.0.1:5000
```

## 第四步：打开网站

在浏览器打开：

```text
http://127.0.0.1:5000
```

## 手机浏览器版本

现在做的是手机浏览器可用的网页版本，不是真正的手机 App。

如果网站运行在你的电脑上，手机需要和电脑连接同一个 Wi-Fi。之后可以把 `127.0.0.1` 换成电脑的局域网地址，例如：

```text
http://电脑IP地址:5000
```

后面我们可以再加一个“让手机访问电脑网站”的步骤。

## PWA 预备结构

当前仍然保持简单的 Flask 架构，但已经加入 PWA 所需的基础文件：

- `static/manifest.json`：应用名称、主题色、启动地址、桌面图标信息
- `static/service-worker.js`：预留离线缓存结构，目前先缓存静态资源
- `static/app.js`：在浏览器中注册 service worker
- `static/icons/icon.svg`：临时应用图标

后续要做“添加到手机桌面”和“离线复习”时，可以继续扩展这些文件。

## 部署到公网

如果你希望手机在外面也能访问，需要把网站部署到 Render 或 Railway 这类云平台。

当前项目已经准备好这些部署文件：

- `requirements.txt`：安装 Flask 和 gunicorn
- `Procfile`：Railway/Heroku 风格启动命令
- `render.yaml`：Render Blueprint 配置
- `runtime.txt`：指定 Python 版本
- `.gitignore`：避免上传本地缓存和本地数据库

云端启动命令：

```text
gunicorn app:app --bind 0.0.0.0:$PORT
```

注意：现在仍然使用 SQLite。Render 或 Railway 的免费环境可能会重启或重建，SQLite 文件不一定长期稳定保存。学习测试阶段可以先这样用；后续真正长期使用，建议升级到 PostgreSQL。

## Push 到 GitHub

第一步，在当前文件夹初始化 Git：

```powershell
cd "C:\Users\lenovo\Documents\单运来"
git init
git add .
git commit -m "Initial German study Flask app"
```

第二步，在 GitHub 创建一个新仓库，例如：

```text
german-study-flask
```

第三步，把本地项目推送到 GitHub。把下面的地址换成你自己的 GitHub 仓库地址：

```powershell
git branch -M main
git remote add origin https://github.com/你的用户名/german-study-flask.git
git push -u origin main
```

如果电脑没有登录 GitHub，命令行会提示你登录或输入 token。

## 部署到 Render

1. 打开 https://render.com
2. 登录后点击 New
3. 选择 Web Service
4. 连接你的 GitHub 仓库
5. Render 通常会自动识别 `render.yaml`
6. 如果手动填写，使用：

```text
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app --bind 0.0.0.0:$PORT
```

7. 创建服务后等待部署完成
8. Render 会给你一个公网网址，手机在外面也可以访问

## 部署到 Railway

1. 打开 https://railway.app
2. 登录后点击 New Project
3. 选择 Deploy from GitHub repo
4. 选择你的 GitHub 仓库
5. Railway 会读取 `requirements.txt`
6. 如果需要手动设置启动命令，填写：

```text
gunicorn app:app --bind 0.0.0.0:$PORT
```

7. 部署完成后，在 Settings 或 Deployments 里生成公网域名
8. 用手机打开这个域名即可访问

## 每天怎么用

1. 先打开“今日复习”
2. 会的单词点“记住了”
3. 不会的单词点“忘记”
4. 新学的词去“单词管理”添加
5. 做题错了，就分别记到“阅读错题”或“听力错题”
6. 好用的句子放到“写作模板”

## 导入单词

进入“单词”页面，点击“导入单词”。

长期使用时，推荐每个单词都按这个结构整理：

```text
单词:
词性:
复数:
中文:

搭配:
- 

例句:
- 德语句子
  中文翻译

近义词:
- A = 
- B = 

语法:
- 

等级:
- 
```

CSV 推荐字段：

```text
german,part_of_speech,plural_form,chinese,collocations,examples,synonyms,grammar_notes,level_text
```

最少需要：

```text
german,chinese
```

也可以直接粘贴结构化文本：

```text
单词: Gewürz
词性: das
复数: die Gewürze
中文: 香料；调味料

搭配:
- scharfe Gewürze = 辛辣香料
- mit Gewürzen kochen = 用香料做饭

例句:
- Dieses Gericht enthält viele Gewürze.
  这道菜里含有很多香料。

近义词:
- Gewürz = 具体香料
- Würze = 调味感；风味

语法:
- mit + Dativ

等级:
- B1 高频
```

## 清理残缺词条

如果批量导入时格式不对，可能会产生残缺卡片。进入“单词”页面，点击“残缺词条”。

系统会保留“只缺少扩展信息”的词条，因为这些词条的单词、中文、词性、复数仍然完整。批量删除只会删除缺少基础字段的词条，例如缺少单词、中文、词性或复数。你可以勾选多个词条后点击“删除选中”。

## 清理重复词条

系统会阻止以后重复导入同一个德语单词。判断时会忽略首尾空格、连续空格和大小写。

如果已经有重复词条，进入“单词”页面，点击“重复词条”。系统会按德语单词分组，每组保留最早添加的一条，点击“删除所有重复项”即可清理后面的重复项。

## 间隔复习规则

- 新单词：今天复习
- 第 1 级：1 天后
- 第 2 级：2 天后
- 第 3 级：4 天后
- 第 4 级：7 天后
- 第 5 级：15 天后
- 第 6 级：30 天后

## 文件说明

- `app.py`：网站的主要 Python 代码
- `templates/`：网页页面
- `static/style.css`：页面样式
- `words.db`：自动生成的 SQLite 数据库
