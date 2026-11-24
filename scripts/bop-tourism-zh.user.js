// ==UserScript==
// @name         LMU BoP Tourism 简体中文
// @namespace    lmu-data-analysis
// @version      0.1.0
// @description  汉化 LMU BoP Tourism 界面、成绩、图表及正文
// @match        https://bop-tourism.com/*
// @match        https://www.bop-tourism.com/*
// @run-at       document-start
// @noframes
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// ==/UserScript==

(() => {
    'use strict';

    const enabled = GM_getValue('chinese-ui', true);
    GM_registerMenuCommand(enabled ? '恢复英文（刷新页面）' : '启用中文（刷新页面）', () => {
        GM_setValue('chinese-ui', !enabled);
        location.reload();
    });
    if (!enabled) return;

    // 词典用于完整标签，避免误改车型、车手名、来源缩写和数据。
    const labels = new Map(Object.entries({
        'skip to main content': '跳转到正文',
        'home': '首页',
        'current': '当前',
        'current bop': '当前 BoP',
        'tables': 'BoP 表',
        'evolution': 'BoP 变化趋势',
        'bop history': 'BoP 历史',
        'bop tourism': 'BoP 数据查询',
        'bop & lap time tools': 'BoP 与圈速工具',
        'patches': '补丁',
        'patch notes': '补丁说明',
        'view patches': '查看补丁',
        'lap times': '圈速',
        'lap time': '圈速',
        'lap time (s)': '圈速（秒）',
        'lap time by track': '各赛道圈速',
        'lmu lap times by track': 'LMU 各赛道圈速',
        'distribution': '圈速分布',
        'lap time distribution': '圈速分布',
        'leaderboard': '圈速榜',
        'leaderboards': '圈速榜',
        'lmu leaderboards': 'LMU 圈速榜',
        'how these boards are built': '榜单统计规则',
        'tiers': '圈速分档',
        'tier': '档位',
        'lap time tiers': '圈速分档',
        'race pace tiers': '正赛节奏分档',
        'pace tiers': '圈速分档',
        'lmu lap time tiers': 'LMU 圈速分档',
        'the six bands': '六个档位',
        'share of field': '车手占比',
        'means': '含义',
        'alien': '顶尖',
        'gold': '金牌',
        'silver': '银牌',
        'bronze': '铜牌',
        'rookie': '新手',
        'offline': '休闲',
        'waiting on race data': '等待赛事数据',
        'weekly': '每周赛事',
        'weekly races': '每周赛事',
        'daily races': '每日赛事',
        'championship': '锦标赛',
        'special events': '特殊赛事',
        'race schedule': '赛事日程',
        'schedule': '日程',
        'lmu daily race schedule and weekly races': 'LMU 每日与每周赛事日程',
        'times in': '显示时区',
        'use my timezone': '使用我的时区',
        'next start': '下一场开赛',
        'picks': '选车推荐',
        'qualifying tiers': '排位圈速分档',
        'top-split class results only': '仅统计最高分组的组别成绩',
        'full': '查看完整数据',
        'src': '来源',
        'win%': '胜率',
        'pod%': '领奖台率',
        'this week': '本周',
        'next week': '下周',
        'previous week': '上周',
        'stats': '赛事统计',
        'race stats': '赛事统计',
        'race data': '赛事数据',
        'pick %': '选用率',
        's1 win %': '最高分组胜率',
        's1 podium %': '最高分组领奖台率',
        's1 win / podium %': '最高分组胜率／领奖台率',
        'win / podium % (all splits)': '所有分组胜率／领奖台率',
        'races available': '可参赛场次',
        'how to read this table': '表格阅读说明',
        'strength': '赛车实力',
        'car strength': '赛车实力',
        'scope': '统计范围',
        'all major tracks': '所有主要赛道',
        'layout variants excluded.': '不计入赛道变体布局。',
        'show circuits': '显示赛道',
        'hide circuits': '隐藏赛道',
        'score': '评分',
        'avg gap': '平均差距',
        'worst': '最大差距',
        'lower score = stronger car. score = 60% avg gap + 40% worst gap across selected tracks.': '评分越低，赛车实力越强。评分按所选赛道的平均差距（60%）和最大差距（40%）计算。',
        'setups': '调校',
        'setup shops': '调校商店',
        'compare packs': '比较调校包',
        'compare setups': '比较调校',
        'setup lap times by car': '各车型的调校圈速',
        'guides': '攻略',
        'featured guide': '精选攻略',
        'read guide': '阅读攻略',
        'bot': '机器人',
        'discord bot': 'Discord 机器人',
        'add to discord': '添加到 Discord',
        'commands': '命令',
        'slash commands': '斜杠命令',
        'report': '反馈',
        'report a bug, ask for a feature': '报告问题或提出功能建议',
        'bugs': '问题',
        'features': '功能',
        'feedback': '反馈',
        'planned': '已计划',
        'shipped': '已发布',
        'reply': '回复',
        'sign in': '登录',
        'sign in with discord': '使用 Discord 登录',
        'sign out': '退出登录',
        'back': '返回',
        'pick a view of': '选择要查看的页面',
        'pick class for': '选择赛车组别',
        'activity': '动态',
        'loading': '正在加载',
        'loading...': '正在加载…',
        'loading…': '正在加载…',
        'analysis': '分析',
        'all': '全部',
        'all classes': '所有组别',
        'car class': '赛车组别',
        'class': '组别',
        'track': '赛道',
        'tracks': '赛道',
        'circuit': '赛道',
        'all tracks': '所有赛道',
        'explore by track': '按赛道浏览',
        'pick a track': '选择赛道',
        'select track': '选择赛道',
        'select a track': '选择赛道',
        'select a car': '选择车型',
        'select a class': '选择赛车组别',
        'layout': '赛道布局',
        'car': '车型',
        'cars': '车型',
        'best cars': '最快车型',
        'apply': '应用',
        'reset': '重置',
        'clear': '清除',
        'filter': '筛选',
        'search': '搜索',
        'sort by': '排序方式',
        'cancel': '取消',
        'close': '关闭',
        'show all': '显示全部',
        'show less': '收起',
        'view details': '查看详情',
        'view profile': '查看详情',
        'setup': '调校',
        'setup mode': '调校模式',
        'fixed setup': '固定调校',
        'fixed setups': '固定调校',
        'open setup': '开放调校',
        'open setups': '开放调校',
        'fixed': '固定调校',
        'open': '开放调校',
        'beginner': '入门',
        'intermediate': '中级',
        'advanced': '高级',
        'race advisor': '选车建议',
        "today's race picks": '今日推荐车型',
        'meta pick': '热门之选',
        'safe pick': '稳妥之选',
        'top pick': '首选',
        'strong pick': '强势车型',
        'form pick': '近期强势',
        'pace pick': '速度之选',
        'sleeper': '潜力车型',
        'high': '高',
        'medium': '中',
        'low': '低',
        'confidence': '置信度',
        'pick rate': '选用率',
        'win rate': '胜率',
        'podium rate': '领奖台率',
        'top-split win rate': '最高分组胜率',
        'top-split podium rate': '最高分组领奖台率',
        'top split': '最高分组',
        'coverage': '覆盖率',
        'best class': '优势组别',
        'fastest benchmark': '最快基准圈速',
        'benchmark type': '基准圈速类型',
        'setup-shop qualifying lap': '调校商店排位圈',
        'game version': '游戏版本',
        'latest bop patch': '最新 BoP 补丁',
        'current version': '当前版本',
        'current patch': '当前补丁',
        'updated': '更新日期',
        'last updated': '最后更新',
        'last raced': '最近参赛',
        'best time': '最佳圈速',
        'time': '用时',
        'version': '版本',
        'source': '来源',
        'driver': '车手',
        'drivers': '车手',
        'validity': '有效性',
        'valid': '有效',
        'delta': '差距',
        'gap': '差距',
        'gap to leader': '距榜首差距',
        'rank': '排名',
        'session': '赛段类型',
        'race': '正赛',
        'races': '场次',
        'race length': '正赛时长',
        'qualifying': '排位赛',
        'quali': '排位赛',
        'qualifying best': '排位最佳圈',
        'best quali': '排位最佳圈',
        'best qualifying lap': '排位最佳圈',
        'race pace': '正赛节奏',
        'race median': '正赛圈速中位数',
        'vs quali': '对比排位',
        'best race': '正赛最佳圈',
        'best race lap': '正赛最佳圈',
        'fastest race lap': '正赛最快圈',
        'best lap': '最快圈',
        'fastest lap': '最快圈',
        'lap': '圈速',
        'laps': '圈数',
        'finish': '完赛名次',
        'median': '中位数',
        'median lap': '圈速中位数',
        'median lap time': '圈速中位数',
        'average': '平均值',
        'minimum': '最小值',
        'maximum': '最大值',
        'percentile': '百分位',
        'driver count': '车手人数',
        'number of drivers': '车手人数',
        'sample size': '样本量',
        'race sample': '赛事样本',
        'results': '成绩',
        'recent results': '近期成绩',
        'latest results': '最新成绩',
        'full result': '完整成绩',
        'full results': '完整成绩',
        'split': '分组',
        'split winner': '分组冠军',
        'ahead of you': '在你前一位',
        'you': '你',
        'level': '持平',
        'my personal bests': '我的最佳成绩',
        'see my personal bests': '查看我的最佳成绩',
        'your le mans ultimate personal best laps': '你在 LMU 的个人最佳圈速',
        'your driver profile': '你的车手档案',
        'driver rating': '车手评级',
        'safety rating': '安全评级',
        'personal best': '个人最佳',
        'races recorded': '已记录赛事',
        'most driven car': '最常驾驶的车型',
        'totals': '总计',
        'last race analysis': '最近一场正赛分析',
        'how race analysis works': '正赛分析说明',
        'your last race': '你最近的一场正赛',
        'race, stint by stint': '正赛各赛段表现',
        'the race, stint by stint': '正赛各赛段表现',
        'lap spread': '圈速分布',
        'lap spread, stint by stint': '各赛段圈速分布',
        'lap time spread': '圈速分布',
        'lap time spread by stint': '各赛段圈速分布',
        'stint': '赛段',
        'stints': '赛段',
        'clean': '有效圈',
        'clean laps': '有效圈',
        'best': '最快圈',
        'tyres': '轮胎',
        'tires': '轮胎',
        'soft': '软胎',
        'hard': '硬胎',
        'wet': '雨胎',
        'medium tyre': '中性胎',
        'medium tire': '中性胎',
        'pit': '进站',
        'in the pits': '维修区耗时',
        'pit lane': '维修区通道',
        'pit stops': '进站次数',
        'pit time': '维修区耗时',
        'pre-bop': 'BoP 更新前',
        'earlier bop': '旧版 BoP',
        'public leaderboard': '公开圈速榜',
        'hide my name': '隐藏我的名字',
        'show my name': '显示我的名字',
        'link steam': '绑定 Steam',
        'unlink steam': '解除 Steam 绑定',
        'unlink': '解除绑定',
        'delete account': '删除账号',
        'delete this account': '删除此账号',
        'erase my lap history': '清除我的圈速记录',
        'what we store': '数据存储说明',
        'about': '关于本站',
        'methodology': '统计方法',
        'contact': '联系',
        'privacy policy': '隐私政策',
        'cookie policy': 'Cookie 政策',
        'terms of use': '使用条款',
        'cookie settings': 'Cookie 设置',
        'your privacy choices': '隐私选项',
        'strictly necessary': '必要 Cookie',
        'always on': '始终启用',
        'analytics': '访问统计',
        'advertising': '广告',
        'reject all': '全部拒绝',
        'save choices': '保存选项',
        'accept all': '全部接受',
        'select a car class and track to compare the fastest recorded lap times across all sources.': '选择赛车组别和赛道，比较各来源记录的最快圈速。',
        'data aggregated from gosetups, bealien, and hymo.': '数据汇总自 GoSetups、BeAlien 和 Hymo。',
        'the median is your sustained race pace and it is the number with a tier beside it. best lap has none since it is less representative of your true pace.': '圈速中位数用于衡量你能持续跑出的正赛节奏，因此旁边标有档位。单圈最快成绩较难代表整体表现，所以不标档位。',
        'use the discord bot': '使用 Discord 机器人',
        'faster valid older lap': '旧版有效圈更快',
        'how lap selection works': '圈速选取规则',
        'data on this page is cached and may be up to 24h old. for live figures,': '本页数据最多延迟 24 小时。查看实时数据请',
        'data on this page is cached and may be up to 48h old. for live figures,': '本页数据最多延迟 48 小时。查看实时数据请',
    }));

    const tracks = new Map(Object.entries({
        'bahrain international circuit': '巴林国际赛道',
        'bahrain international circuit outer': '巴林国际赛道外圈',
        'bahrain international circuit paddock': '巴林国际赛道围场布局',
        'bahrain international circuit endurance': '巴林国际赛道耐力赛布局',
        'cota': '美洲赛道（COTA）',
        'cota national': '美洲赛道国家布局',
        'circuit paul ricard': '保罗·里卡尔赛道',
        'circuit de barcelona': '巴塞罗那赛道',
        'circuit de spa-francorchamps': '斯帕-弗朗科尔尚赛道',
        'circuit de la sarthe (le mans)': '萨尔特赛道（勒芒）',
        'circuit de la sarthe mulsanne (le mans mulsanne)': '萨尔特赛道（穆尔桑布局）',
        'daytona international speedway': '代托纳国际赛道',
        'fuji speedway': '富士赛道',
        'fuji speedway classic': '富士赛道经典布局',
        'imola': '伊莫拉',
        'interlagos': '因特拉戈斯',
        'laguna seca': '拉古纳塞卡',
        'long beach': '长滩赛道',
        'monza': '蒙扎',
        'monza curva grande': '蒙扎 Curva Grande 布局',
        'portimão': '波尔蒂芒',
        'qatar': '卡塔尔赛道',
        'qatar short': '卡塔尔赛道短布局',
        'road atlanta': '亚特兰大公路赛道',
        'sebring international raceway': '赛百灵国际赛道',
        'sebring school': '赛百灵教学布局',
        'silverstone': '银石',
        'silverstone international': '银石国际布局',
        'silverstone national': '银石国家布局',
    }));
    const tierNames = 'Alien|Gold|Silver|Bronze|Rookie|Offline';
    const tierGap = new RegExp(`^([\\d.]+)\\s*s\\s+(to|inside|into)\\s+(${tierNames})$`, 'i');
    const tierDifference = new RegExp(`^([\\d.]+)\\s*s\\s+(ahead of|behind)\\s+(${tierNames})$`, 'i');
    const groups = '(GT3|Hypercar|HY|LMP2|LMP3)';
    const formats = [
        [new RegExp(`^${groups} (?:at|·) (.+)$`, 'i'), (_, group, track) => `${group} · ${trackName(track)}`],
        [new RegExp(`^LMU ${groups} (race stats|car strength ranking)$`, 'i'),
            (_, group, heading) => `LMU ${group} ${heading.toLowerCase() === 'race stats' ? '赛事统计' : '赛车实力排名'}`],
        [new RegExp(`^${groups} [-—–] (fixed setup|open setup)$`, 'i'), (_, group, setup) => `${group} · ${label(setup)}`],
        [new RegExp(`^${groups} [-—–] all (\\d+) tracks$`, 'i'), (_, group, count) => `${group} · 全部 ${count} 条赛道`],
        [/^(GT3|Hypercar|HY|LMP2|LMP3) (beginner|intermediate|advanced) (open|fixed)$/i,
            (_, group, rank, setup) => `${group} · ${label(rank)} · ${label(setup)}`],
        [/^(meta pick|safe pick|top pick|strong pick|form pick|pace pick|sleeper) (high|medium|low)$/i,
            (_, pick, confidence) => `${label(pick)} · 置信度${label(confidence)}`],
        [/^(?:under|less than) (\d+) min(?:utes?)?$/i, (_, minutes) => `少于 ${minutes} 分钟`],
        [/^(\d+)\s*(?:to|–|-|—)\s*(\d+) min(?:utes?)?$/i, (_, low, high) => `${low}–${high} 分钟`],
        [/^(?:(\d+)\+ min(?:utes?)?|(?:over|more than) (\d+) min(?:utes?)?)$/i, (_, atLeast, over) =>
            atLeast ? `${atLeast} 分钟及以上` : `超过 ${over} 分钟`],
        [/^top\s*([\d.]+%)$/i, (_, percentile) => `前 ${percentile}`],
        [/^([\d.]+)\s+pts?\s+(ahead|back|behind)$/i, (_, points, direction) =>
            `${direction.toLowerCase() === 'ahead' ? '领先' : '落后'} ${points} 个百分点`],
        [tierGap, (_, seconds, direction, tier) =>
            `${direction.toLowerCase() === 'to' ? '距' : '快于'}${label(tier)}门槛 ${seconds} 秒`],
        [tierDifference, (_, seconds, direction, tier) =>
            `${direction.toLowerCase() === 'behind' ? '慢于' : '快于'}${label(tier)}门槛 ${seconds} 秒`],
        [/^show all (\d+)$/i, (_, count) => `显示全部 ${count} 项`],
        [/^track (\d+)(?: (\*|\(optional\)))?$/i, (_, number, hint) =>
            `赛道 ${number}${hint === '*' ? ' *' : hint ? '（可选）' : ''}`],
        [/^all major tracks \((\d+) circuits\)$/i, (_, count) => `所有主要赛道（${count} 条）`],
        [/^(\d+) cars · (\d+) with entries$/i, (_, total, entered) => `${total} 款车型，${entered} 款有参赛记录`],
        [/^sr (gold|silver|bronze)$/i, (_, tier) => `SR ${label(tier)}`],
        [/^(gold|silver|bronze) SR or higher to enter$/i, (_, tier) => `参赛要求：安全评级（SR）达到${label(tier)}或以上`],
        [/^every (\d+) min, (\d+) min session with qualifying$/i,
            (_, repeat, duration) => `每 ${repeat} 分钟开赛，赛程共 ${duration} 分钟（含排位）`],
        [/^(\d+) starts? this week$/i, (_, count) => `本周开赛 ${count} 场`],
        [/^(all|today's) start times \(([^)]+)\)$/i,
            (_, scope, zone) => `${scope.toLowerCase() === 'all' ? '全部' : '今日'}开赛时间（${zone}）`],
        [/^([\d,]+) drivers who qualified here$/i, (_, count) => `${count} 位车手在此跑出排位成绩`],
        [/^(\d+) cars?$/i, (_, count) => `${count} 款车型`],
        [/^(\d+) tracks?$/i, (_, count) => `${count} 条赛道`],
        [/^(\d+) laps?$/i, (_, count) => `${count} 圈`],
        [/^split (\d+)$/i, (_, split) => `第 ${split} 分组`],
        [/^stint (\d+)$/i, (_, stint) => `第 ${stint} 赛段`],
        [/^driver ([0-9a-f]{4})$/i, (_, id) => `车手 ${id}`],
        [/^(last raced|updated|last updated)\s*:?\s+(.+)$/i, (_, caption, date) => `${label(caption)} ${date}`],
        [/^(current version|latest bop patch|current patch):\s*(\S.*)$/i,
            (_, caption, version) => `${label(caption)}：${version}`],
    ];

    function label(text) {
        return labels.get(text.toLowerCase()) ?? text;
    }

    function trackName(text) {
        return tracks.get(text.toLowerCase())
            ?? text.replace(/^Circuit Paul Ricard (1A(?:-V2(?:-Short)?)?|3A)$/i, '保罗·里卡尔赛道 $1');
    }

    function translateLabel(value, element) {
        if (typeof value !== 'string' || !/[A-Za-z]/.test(value)) return value;

        const [, leading, content, trailing] = value.match(/^(\s*)(.*?)(\s*)$/s);
        const [, body, suffix = ''] = content.match(/^(.*?)(\s*[→›↗:]\s*)?$/s);
        const key = body.replace(/\s+/g, ' ').trim();
        const lower = key.toLowerCase();
        let result = labels.get(lower) ?? trackName(key);

        if (['setup', 'setups'].includes(lower) && element?.closest('nav a[href="/setups"]')) {
            result = '调校商店';
        }
        if (lower === 'medium' && element?.closest('td')) result = '中性胎';
        if (result === key) {
            for (const [pattern, replacement] of formats) {
                if (!pattern.test(key)) continue;
                result = key.replace(pattern, replacement);
                break;
            }
        }
        return result === key ? value : leading + result + suffix + trailing;
    }

    // 仅在当前站点绘制已知 Canvas 标签；测量与绘制采用同一文本。
    function localizeCanvas(contextType) {
        if (!contextType) return;
        for (const method of ['fillText', 'strokeText', 'measureText']) {
            const original = contextType.prototype[method];
            if (typeof original !== 'function') continue;
            try {
                contextType.prototype[method] = function (...args) {
                    if (args.length) args[0] = translateLabel(args[0]);
                    return Reflect.apply(original, this, args);
                };
            } catch {
                // 浏览器禁止修改绘图方法时，仍继续处理普通页面和 SVG。
            }
        }
    }

    localizeCanvas(unsafeWindow.CanvasRenderingContext2D);
    localizeCanvas(unsafeWindow.OffscreenCanvasRenderingContext2D);

    const skipSelector = [
        'script', 'style', 'noscript', 'template', 'textarea', 'input',
        'kbd', 'samp', 'code', 'pre', '[contenteditable]:not([contenteditable="false"])',
        '[translate="no"]', '[data-lmu-zh]',
    ].join(',');
    const attributes = ['title', 'aria-label', 'placeholder', 'label'];
    const attributeSelector = attributes.map(name => `[${name}]`).join(',');
    const originalText = new WeakMap();
    const optionValues = new WeakMap();
    const queued = new Set();
    let frame = 0;

    function sourceOf(node) {
        const saved = originalText.get(node);
        return saved?.translated === node.data ? saved.original : node.data;
    }

    function setText(node, original, translated) {
        if (node.data === translated) return;
        originalText.set(node, { original, translated });
        node.data = translated;
    }

    function visitText(root, action) {
        if (root.nodeType === Node.TEXT_NODE) {
            action(root);
            return;
        }
        const iterator = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        for (let node = iterator.nextNode(); node; node = iterator.nextNode()) action(node);
    }

    function translateText(node) {
        const parent = node.parentElement;
        if (!parent || parent.closest(skipSelector) || originalText.get(node)?.translated === node.data) return;

        const original = node.data;
        const result = translateLabel(original, parent);
        const option = parent.closest('option');
        if (option) {
            const saved = optionValues.get(option);
            if (!option.hasAttribute('value') && result !== original) {
                optionValues.set(option, option.value);
                option.value = option.value;
            } else if (saved !== undefined && option.value === saved) {
                option.removeAttribute('value');
                optionValues.set(option, option.value);
                option.value = option.value;
            }
        }
        setText(node, original, result);
    }

    function translateAttributes(element) {
        if (element.closest(skipSelector) && !element.matches('input:not([type="hidden"])')) return;
        for (const attribute of attributes) {
            const value = element.getAttribute(attribute);
            const result = translateLabel(value, element);
            if (result !== value) element.setAttribute(attribute, result);
        }
    }

    function scan(root) {
        if (!root.isConnected || root.parentElement?.closest(skipSelector)) return;
        visitText(root, translateText);
        if (root.nodeType !== Node.ELEMENT_NODE) return;
        translateAttributes(root);
        for (const element of root.querySelectorAll(attributeSelector)) translateAttributes(element);
    }

    function schedule(node) {
        if (!node?.isConnected) return;
        queued.add(node);
        if (!frame) frame = requestAnimationFrame(flush);
    }

    function flush() {
        frame = 0;
        const roots = Array.from(queued).filter(node => {
            for (let parent = node.parentElement; parent; parent = parent.parentElement) {
                if (queued.has(parent)) return false;
            }
            return true;
        });
        queued.clear();
        roots.forEach(scan);
    }

    function observe(mutations) {
        for (const mutation of mutations) {
            if (mutation.type === 'attributes') {
                translateAttributes(mutation.target);
            } else if (mutation.type === 'characterData') {
                const node = mutation.target;
                if (originalText.get(node)?.translated !== node.data) schedule(node);
            } else {
                mutation.addedNodes.forEach(schedule);
            }
        }
    }

    const proseSelector = [
        'p', 'li', 'blockquote', 'figcaption', 'dd', 'summary',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    ].join(',');
    const proseTranslations = new WeakMap();
    let running = false;
    let control;
    let status;

    function addProseControl() {
        const host = document.createElement('div');
        host.setAttribute('data-lmu-zh', '');
        Object.assign(host.style, {
            position: 'fixed', right: '12px', bottom: '12px', zIndex: '10000',
        });
        const shadow = host.attachShadow({ mode: 'open' });
        const style = document.createElement('style');
        style.textContent = `
            :host { font: 14px system-ui, sans-serif; color: #fff; }
            button, output { background: #23252b; color: #fff; border: 1px solid #626670;
                border-radius: 6px; padding: 6px 10px; font: inherit; }
            button { cursor: pointer; }
            button:disabled { cursor: progress; }
            output { display: block; margin-bottom: 4px; max-width: 250px; }
            output:empty { display: none; }
        `;
        status = document.createElement('output');
        status.setAttribute('aria-live', 'polite');
        control = document.createElement('button');
        control.type = 'button';
        control.textContent = '翻译正文';
        control.addEventListener('click', translateProse);
        shadow.append(style, status, control);
        document.body.append(host);
        GM_registerMenuCommand('定位正文翻译按钮', () => control.focus());
    }

    function proseSource(block) {
        const nodes = [];
        visitText(block, node => {
            if (!node.parentElement?.closest(skipSelector)) nodes.push(node);
        });
        return nodes;
    }

    function showTranslation(block, nodes, original, translation) {
        if (nodes.filter(node => node.data.trim()).length === 1) {
            const node = nodes.find(item => item.data.trim());
            const [, leading, , trailing] = node.data.match(/^(\s*)(.*?)(\s*)$/s);
            setText(node, sourceOf(node), leading + translation + trailing);
        } else {
            // 含链接的段落显示对照译文，保留原有链接和样式。
            const note = document.createElement('span');
            note.setAttribute('data-lmu-zh', '');
            note.lang = 'zh-Hans';
            note.style.display = 'block';
            note.style.marginBlockStart = '0.25em';
            note.textContent = translation;
            block.append(note);
        }
        proseTranslations.set(block, original);
    }

    async function translateProse(event) {
        if (!event.isTrusted || running) return;
        const api = globalThis.Translator ?? unsafeWindow.Translator;
        if (!api) {
            status.textContent = '当前浏览器未提供本地翻译模型。常用界面已由脚本翻译。';
            return;
        }
        running = true;
        control.disabled = true;
        status.textContent = '正在准备本地翻译…';
        let session;
        try {
            const options = { sourceLanguage: 'en', targetLanguage: 'zh-Hans' };
            options.monitor = monitor => {
                monitor.addEventListener('downloadprogress', ({ loaded }) => {
                    status.textContent = `正在下载本地模型… ${Math.round(loaded * 100)}%`;
                });
            };
            if (await api.availability(options) === 'unavailable') {
                status.textContent = '当前浏览器未提供英语到简体中文的本地模型。';
                return;
            }
            session = await api.create(options);
            const main = document.querySelector('main,[role="main"]') ?? document.body;
            let done = 0;
            for (const block of main.querySelectorAll(proseSelector)) {
                if (!block.isConnected || block.closest(`${skipSelector},nav,footer,button,[role="button"]`)
                    || block.querySelector(proseSelector) || !block.getClientRects().length) continue;
                const nodes = proseSource(block);
                const original = nodes.map(sourceOf).join('').trim();
                const displayed = nodes.map(node => node.data).join('').trim();
                if (original === proseTranslations.get(block)
                    || !/[A-Za-z]{2,}\s+[A-Za-z]{2,}/.test(displayed)
                    || (block.matches('li,h1,h2,h3,h4,h5,h6') && original.split(/\s+/).length < 5)) continue;
                const translated = await session.translate(original);
                if (!block.isConnected || original !== proseSource(block).map(sourceOf).join('').trim()
                    || !translated || translated === original) continue;
                block.querySelector(':scope > [data-lmu-zh]')?.remove();
                showTranslation(block, proseSource(block), original, translated);
                status.textContent = `已翻译 ${++done} 处正文…`;
            }
            status.textContent = done ? `已翻译 ${done} 处正文。` : '当前可见正文已处理。';
        } catch (error) {
            const message = error?.name === 'NotAllowedError'
                ? '浏览器暂无法加载翻译模型。请更新浏览器后重试。'
                : '本地翻译暂时不可用。已完成的译文会保留。';
            status.textContent = message;
        } finally {
            session?.destroy();
            control.disabled = false;
            running = false;
        }
    }

    function start() {
        scan(document.documentElement);
        addProseControl();
        new MutationObserver(observe).observe(document.documentElement, {
            subtree: true, childList: true, characterData: true,
            attributes: true, attributeFilter: attributes,
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start, { once: true });
    } else {
        start();
    }
})();
