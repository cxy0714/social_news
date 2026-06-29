# Daily News Digest — Instruction for Claude Code（云端定时任务版）

> 本文件是给 **Claude Code 云端定时任务（Cloud Scheduled Task / Routine）** 的运行说明。
> 形态：每天凌晨在 Anthropic 云端自动运行（Max 可用，电脑关机也跑）——用 Claude **自带的网页搜索/抓取能力**巡视主流报纸，挑出**全类型要闻（政治·国际 / 经济·财经 / 科技 / 社会·民生 / 灾害·突发）**，写中文摘要，提交到本（私有）仓库。
> **不需要**本地开机、不需要自建爬虫脚本、不需要 GitHub Pages。

---

## 0. 运行环境与前提（先读这一节）

- **运行位置**：Claude Code 云端。机器关机也会按计划跑。
- **自主运行、无审批弹窗**：因此「触发提示」和本文件必须自洽、明确。
- **必须在云环境中开启网络访问（Network access）**，否则抓不到新闻——这是新闻任务最常见的失败原因。
- **私有仓库可用**：通过 GitHub 连接器克隆你权限内的私有库。
- **状态靠 git 持久化**：每次运行是全新克隆、跨次无记忆。所谓「归档」= 已 commit 进仓库的文件。所以每天**必须 commit & push**。
- **分支限制**：默认只能 push 到 `claude/` 前缀分支。若要直接更新主分支上的 digest，给该仓库开启 **Allow unrestricted branch pushes**，或固定推到一个 `news` 分支。

---

## 1. 每日工作流（Claude 用自带能力执行，不写爬虫）

1. 读取第 4 节「来源清单」。
2. 用 `web_search` / `web_fetch` 巡视各源最近 24 小时的社会新闻（**不依赖 RSS 脚本**；RSS 链接仅作命中提示）。
3. 覆盖**全类型要闻**，按 5 大类筛选并**去重**：**政治·国际 / 经济·财经 / 科技 / 社会·民生 / 灾害·突发**。每类保留约 3–8 条高价值条目（社会类可适当多一些），体育/娱乐花边按需少量或略。
4. 每条用**自己的话**写 1–2 句中文摘要（≤ 50 字），保留原标题（可附中文译题），附原文链接。
5. 打标签：region（北美/欧洲/中国大陆/港澳台/亚太/中东/拉美/全球等）作来源地标注；按上述 5 大类分区组织。
6. 写文件 `digests/YYYY-MM-DD.md`（格式见第 3 节，**按类型分区**），并更新 `README.md` 顶部的「最近 7 天」索引。
7. `git add . && git commit -m "news: YYYY-MM-DD" && git push`。

---

## 2. 内容处理规则（版权红线，必须遵守）

- **版权**：只写**原创简短摘要** + **必附原文链接**。禁止复制原文段落、禁止长篇引用（如确需引用，单条 < 15 词且仅一处）。
- **去重**：同一事件多源时合并为一条，主链接选最权威/信息最全者，其余可作「另见」。
- **语言**：摘要中文；原标题保留原文，可附中文译题。
- **付费墙**：WSJ / FT / 经济学人等以公开摘要/标题为准，不绕过。
- **来源标注**：官方通讯社（新华社/TASS/人民日报等）与独立媒体如实标注，不做立场加工。
- **容错**：某些来源不可达就跳过，并在文件末尾注明「本日未覆盖：xxx」。

---

## 3. 输出格式（纯 markdown，私有库内查看）

- `digests/YYYY-MM-DD.md`：当日列表，按区域分组。
- `README.md`：顶部维护「最近 7 天」索引，链接到各日文件。
- **不生成 HTML、不开 Pages。**

每日文件模板（**按 5 大类型分区**，区域作来源标注）：

```markdown
# 每日新闻摘要 · 2026-06-29
> 生成时间：2026-06-29 08:00（北京时间）

## 政治 · 国际
- **[原标题](https://...)** — 中文一句话摘要。`中东` · Gulf News

## 经济 · 财经
- **[原标题](https://...)** — 中文一句话摘要。`全球` · CNBC

## 科技
- **[原标题](https://...)** — 中文一句话摘要。`北美` · CNBC

## 社会 · 民生
- **[原标题](https://...)** — 中文一句话摘要。`港澳台` · 香港01

## 灾害 · 突发
- **[原标题](https://...)** — 中文一句话摘要。`亚太` · NHK

---
_本日未覆盖：xxx, yyy（来源不可达）_
```

---

## 4. 来源清单

> 用 Claude 自带 web 能力巡视下列站点即可。`RSS` 列仅作命中提示（可选）；公开 RSS 常失效，失效就直接抓主页/搜索。

### 北美
| 媒体 | 地区 | 主页 | RSS（提示，可选） |
|---|---|---|---|
| The New York Times | 美国 | https://www.nytimes.com | https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml |
| The Washington Post | 美国 | https://www.washingtonpost.com | https://feeds.washingtonpost.com/rss/national |
| The Wall Street Journal | 美国(付费) | https://www.wsj.com | — |
| USA Today | 美国 | https://www.usatoday.com | https://www.usatoday.com/rss |
| Los Angeles Times | 美国 | https://www.latimes.com | — |
| Associated Press (AP) | 美国/通讯社 | https://apnews.com | — |
| Bloomberg | 美国(付费) | https://www.bloomberg.com | — |
| NPR | 美国 | https://www.npr.org | https://feeds.npr.org/1001/rss.xml |
| Politico | 美国 | https://www.politico.com | https://www.politico.com/rss/politicopicks.xml |
| The Globe and Mail | 加拿大 | https://www.theglobeandmail.com | — |
| Toronto Star | 加拿大 | https://www.thestar.com | — |
| CBC News | 加拿大 | https://www.cbc.ca/news | https://www.cbc.ca/webfeed/rss/rss-topstories |

### 英国 / 欧洲
| 媒体 | 地区 | 主页 | RSS（提示，可选） |
|---|---|---|---|
| BBC News | 英国 | https://www.bbc.com/news | http://feeds.bbci.co.uk/news/world/rss.xml |
| The Guardian | 英国 | https://www.theguardian.com | https://www.theguardian.com/world/rss |
| The Times | 英国(付费) | https://www.thetimes.co.uk | — |
| The Telegraph | 英国 | https://www.telegraph.co.uk | — |
| Financial Times | 英国(付费) | https://www.ft.com | — |
| The Economist | 英国(付费) | https://www.economist.com | — |
| Le Monde | 法国 | https://www.lemonde.fr | https://www.lemonde.fr/rss/une.xml |
| Le Figaro | 法国 | https://www.lefigaro.fr | — |
| AFP（法新社） | 法国/通讯社 | https://www.afp.com | — |
| Der Spiegel | 德国 | https://www.spiegel.de | https://www.spiegel.de/international/index.rss |
| Die Zeit | 德国 | https://www.zeit.de | — |
| FAZ | 德国 | https://www.faz.net | — |
| Süddeutsche Zeitung | 德国 | https://www.sueddeutsche.de | — |
| El País | 西班牙 | https://english.elpais.com | — |
| Corriere della Sera | 意大利 | https://www.corriere.it | — |
| La Repubblica | 意大利 | https://www.repubblica.it | — |
| Politico Europe | 欧盟 | https://www.politico.eu | — |

### 中国大陆
> 大陆媒体公开 RSS 多已停用，优先抓主页 / 搜索。

| 媒体 | 主页 |
|---|---|
| 人民日报 / 人民网 | http://www.people.com.cn |
| 新华社 / 新华网 | http://www.news.cn |
| 央视新闻 | https://news.cctv.com |
| 环球时报 | https://www.huanqiu.com |
| 澎湃新闻 | https://www.thepaper.cn |
| 财新网 | https://www.caixin.com |
| 第一财经 | https://www.yicai.com |
| 界面新闻 | https://www.jiemian.com |
| 南方周末 | https://www.infzm.com |
| 中国新闻网 | https://www.chinanews.com.cn |

### 港澳台
| 媒体 | 地区 | 主页 |
|---|---|---|
| South China Morning Post | 香港 | https://www.scmp.com |
| 明报 | 香港 | https://news.mingpao.com |
| 中央社 CNA | 台湾 | https://www.cna.com.tw |
| 联合报 | 台湾 | https://udn.com |

### 亚太其他
| 媒体 | 地区 | 主页 |
|---|---|---|
| 朝日新闻 Asahi | 日本 | https://www.asahi.com |
| 读卖新闻 Yomiuri | 日本 | https://www.yomiuri.co.jp |
| 日本经济新闻 Nikkei | 日本 | https://www.nikkei.com |
| NHK | 日本 | https://www3.nhk.or.jp/news |
| The Japan Times | 日本(英) | https://www.japantimes.co.jp |
| 朝鲜日报 Chosun | 韩国 | https://www.chosun.com |
| 韩联社 Yonhap | 韩国/通讯社 | https://en.yna.co.kr |
| The Times of India | 印度 | https://timesofindia.indiatimes.com |
| The Hindu | 印度 | https://www.thehindu.com |
| The Straits Times | 新加坡 | https://www.straitstimes.com |
| ABC News | 澳大利亚 | https://www.abc.net.au/news |

### 中东 / 其他 / 通讯社
| 媒体 | 地区 | 主页 | RSS（提示，可选） |
|---|---|---|---|
| Al Jazeera | 卡塔尔 | https://www.aljazeera.com | https://www.aljazeera.com/xml/rss/all.xml |
| TASS | 俄罗斯/通讯社 | https://tass.com | — |
| Meduza | 俄罗斯(独立) | https://meduza.io/en | — |
| Folha de S.Paulo | 巴西 | https://www.folha.uol.com.br | — |
| Reuters | 全球/通讯社 | https://www.reuters.com | — |

---

## 5. 设置云端定时任务（一次性）

创建途径任选其一：
- **网页**：claude.ai/code/scheduled → New scheduled task
- **CLI**：任意会话里运行 `/schedule daily news digest at 3am`
- **桌面端**：Schedule → New task → New remote task

表单填写：
1. **名称 + 提示**：见下方「触发提示」。
2. **仓库**：选择本私有仓库。
3. **环境**：**开启 Network access（关键）**；如需密钥再加环境变量；可选 setup script。
4. **计划**：Daily，选你睡觉时段（如 03:00，本地时区）。最小间隔 1 小时。
5. **分支**：若要直接写主分支 / `news` 分支，开启 Allow unrestricted branch pushes。
6. **连接器**：保留 GitHub，其余按需移除。

**触发提示（粘进任务 prompt，保持简短自洽）：**

```
读取仓库根目录的 instruction.md，按其中“每日工作流”为今天（北京时间）生成一份全类型新闻摘要：
用你的网页搜索/抓取能力巡视 instruction.md 列出的来源，覆盖政治·国际/经济·财经/科技/社会·民生/灾害·突发五大类，
筛选并去重，按类型分区写入 digests/YYYY-MM-DD.md，
更新 README.md 顶部的“最近 7 天”索引，然后 commit 并 push。
严格遵守 instruction.md 的版权规则：只写原创简短摘要并附原文链接，不复制原文。
若某些来源不可达，跳过并在文件末尾注明。
```

---

## 6. 注意事项

- **先 Run now 跑一次**：检查网络是否放开、提交是否成功、摘要质量与去重效果，再开定时。
- **用量**：定时任务与交互会话一样计入订阅用量，另有每日运行次数上限；每天一次对 Max 无压力。
- **想睡醒收到推送**：可加 Slack / 邮件类连接器，让它把当天摘要也发你一份（可选）。
- **时区**：统一按北京时间显示。
- **可调项**：「社会新闻」范围、每区域条数、来源增减，按实际效果迭代。

---

_v2（云端定时任务版）。可按运行情况继续调整。_