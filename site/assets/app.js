// SPDX-License-Identifier: AGPL-3.0-only
import {searchCatalogMatches} from './upstream/catalog-search.js';
import {filterRecords, sortRecords, escapeHTML as e, safeURL, csvCell} from './catalog.js';

const config = JSON.parse(document.getElementById('site-config').textContent);
const base = config.base;
const url = (route = '') => base + route;
const repo = config.repo;
const readLocal = (key, fallback) => { try { return JSON.parse(localStorage.getItem('survey-radar:' + key)) ?? fallback; } catch { return fallback; } };
let lang = ['en', 'zh'].includes(readLocal('language', 'zh')) ? readLocal('language', 'zh') : 'zh';
let saved = readLocal('saved', []), followed = readLocal('followed', []), compared = readLocal('compare', []);
for (const [name, value] of [['saved', saved], ['followed', followed], ['compare', compared]]) {
  if (!Array.isArray(value) || !value.every(v => typeof v === 'string')) {
    if (name === 'saved') saved = []; else if (name === 'followed') followed = []; else compared = [];
  }
}
compared = compared.slice(0,4);
const t = (zh, en) => lang === 'zh' ? zh : en;
const number = value => value == null ? 'N/A' : Number(value).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US');
const persist = (key, value) => { try { localStorage.setItem('survey-radar:' + key, JSON.stringify(value)); } catch { toast(t('浏览器无法保存；本次会话仍可使用。', 'Browser storage unavailable; changes last for this session.')); } };
function toast(message) { const node = document.getElementById('toast'); node.textContent = message; node.classList.add('visible'); clearTimeout(toast.timer); toast.timer = setTimeout(() => node.classList.remove('visible'), 3500); }
function translate() {
  document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-zh][data-en]').forEach(n => { n.textContent = n.dataset[lang]; });
  document.getElementById('language').textContent = lang === 'zh' ? 'EN' : '中';
}
let catalog, records, taxonomy, summary, categoryMap, searchRecords;
let limit = 30, lastResults = [];
const app = document.getElementById('app');
function state() {
  const p = new URLSearchParams(location.search), s = {};
  for (const key of ['q','category','topic','year','venue','source','type','tag','sort']) s[key] = p.get(key) || '';
  for (const key of ['code','saved','followed']) s[key] = p.get(key) === '1';
  s.sort ||= config.route === '' ? 'time' : (s.q ? 'relevance' : 'citations');
  return s;
}
function update(patch, replace = false) {
  const p = new URLSearchParams(location.search);
  for (const [key, value] of Object.entries(patch)) { if (value === '' || value === false || value == null) p.delete(key); else p.set(key, value === true ? '1' : value); }
  history[replace ? 'replaceState' : 'pushState']({}, '', location.pathname + (p.size ? '?' + p : ''));
  limit = 30; render();
}
function categoryName(id) { const c = categoryMap.get(id); return c ? (lang === 'zh' ? c.name_zh : c.name) : id; }
function topicName(p) { const topic = categoryMap.get(p.category)?.topics.find(v => v.id === p.topic); return topic ? (lang === 'zh' ? topic.name_zh : topic.name) : p.topic; }
function link(href, label, className='') { const safe = safeURL(href); return safe ? `<a class="${e(className)}" href="${e(safe)}" target="_blank" rel="noopener noreferrer">${e(label)}</a>` : ''; }
function metric(p) { return number(p.citations) + (p.code_url ? ` <span class="stars">(★ ${number(p.stars)})</span>` : ''); }
function row(p) {
  const tags = Object.values(p.tags).flat().slice(0,3);
  return `<article class="survey-row" data-paper="${p.id}"><div class="row-date"><button class="save-button ${saved.includes(p.id) ? 'selected' : ''}" data-save="${p.id}" aria-pressed="${saved.includes(p.id)}" aria-label="${t('收藏', 'Save')} ${e(p.title)}">${saved.includes(p.id) ? '★' : '☆'}</button><span>${e(p.date || p.year || 'N/A')}</span></div><div class="row-content"><div class="chips"><a class="chip" href="${url('library/')}?category=${p.category}">${e(categoryName(p.category))}</a><span class="chip">${e(p.review_type)}</span></div><h2><a href="${url('papers/' + p.id + '/')}">${e(p.title)}</a></h2><p class="row-authors">${e(p.authors.slice(0,3).join(', '))}${p.authors.length > 3 ? ' et al.' : ''}</p><p class="row-scope">${e(topicName(p))}${tags.length ? ' · ' + e(tags.join(' · ')) : ''}</p><div class="row-meta"><span>${e(p.venue || 'N/A')}</span>${link(p.paper_url, 'Paper ↗')}${link(p.code_url, 'Code ↗')}<span class="row-citations" title="${t('OpenAlex 引用数；括号内为代码仓库 Stars', 'OpenAlex citations; repository stars in parentheses')}">${t('引用', 'Citations')} ${metric(p)}</span><button class="text-button ${compared.includes(p.id) ? 'selected' : ''}" data-compare="${p.id}" aria-pressed="${compared.includes(p.id)}">${compared.includes(p.id) ? '✓ ' : '＋ '}${t('对比','Compare')}</button></div></div></article>`;
}
function select(key, label, values, s, display = v => v) {
  return `<label class="facet"><span>${label}</span><select data-param="${key}"><option value="">${t('全部','All')}</option>${values.map(v => `<option value="${e(v)}" ${String(s[key]) === String(v) ? 'selected' : ''}>${e(display(v))}</option>`).join('')}</select></label>`;
}
function searchAndSort(s) {
  return `<div class="search-bar"><label class="search-box"><span aria-hidden="true">⌕</span><input type="search" id="search" aria-label="${t('搜索综述','Search surveys')}" placeholder="${t('搜索标题、作者、主题、标签…','Search titles, authors, topics, tags…')}" value="${e(s.q)}"><kbd>/</kbd></label><label class="sort-control"><span>${t('排序','Sort by')}</span><select data-param="sort"><option value="citations" ${s.sort==='citations'?'selected':''}>${t('引用数 ↓','Citations ↓')}</option><option value="time" ${s.sort==='time'?'selected':''}>${t('时间 ↓','Newest ↓')}</option><option value="stars" ${s.sort==='stars'?'selected':''}>${t('GitHub Stars ↓','GitHub Stars ↓')}</option><option value="relevance" ${s.sort==='relevance'?'selected':''}>${t('相关性','Relevance')}</option></select></label><button data-action="filters" aria-expanded="${filtersOpen}">${t('筛选','Filters')} ☷</button><button data-action="reset" title="${t('重置筛选','Reset filters')}">↻</button></div>`;
}
let filtersOpen = false;
function filterPanel(s) {
  const all = key => [...new Set(records.map(p => p[key]).filter(Boolean))].sort();
  const topics = s.category ? categoryMap.get(s.category)?.topics || [] : [];
  return `<section class="filter-panel" ${filtersOpen ? '' : 'hidden'} aria-label="${t('筛选条件','Filter options')}">${select('year',t('年份','Year'),all('year').reverse(),s)}${select('venue',t('渠道','Venue'),all('venue'),s)}${select('source',t('数据来源','Source'),[...new Set(records.flatMap(p=>p.sources))].sort(),s)}${select('type',t('综述类型','Review type'),all('review_type'),s)}${select('tag',t('多维标签','Tags'),[...new Set(records.flatMap(p=>Object.values(p.tags).flat()))].sort(),s)}${topics.length ? select('topic', t('二级主题','Subtopic'), topics.map(v=>v.id),s,v=>{const a=topics.find(x=>x.id===v);return lang==='zh'?a.name_zh:a.name;}) : ''}<label class="check"><input type="checkbox" data-param="code" ${s.code?'checked':''}> ${t('含 Code 链接','Has Code link')}</label><p class="quiet">${t('未知引用排在末尾；只有年份的条目排在同年已知日期之后。','Unknown metrics sort last; year-only records follow dated records in that year.')}</p></section>`;
}
function categorySidebar(s) {
  const counts = new Map(); records.forEach(p=>counts.set(p.category,(counts.get(p.category)||0)+1));
  return `<aside class="category-sidebar"><h2>${t('研究方向','Research directions')}</h2><button class="direction ${!s.category?'active':''}" data-category=""><span>${t('全部综述','All surveys')}</span><span>${number(records.length)}</span></button>${taxonomy.map(c=>`<div class="direction-wrap"><button class="direction ${s.category===c.id?'active':''}" data-category="${c.id}"><span>${e(categoryName(c.id))}</span><span>${number(counts.get(c.id)||0)}</span></button><button class="follow-button ${followed.includes(c.id)?'selected':''}" data-follow="${c.id}" aria-pressed="${followed.includes(c.id)}" title="${t('关注方向','Follow direction')}">${followed.includes(c.id)?'✓':'＋'}</button></div>`).join('')}<a class="small-link" href="${url('landscape/')}">${t('查看主题全景 →','Explore the landscape →')}</a></aside>`;
}
function results(s) {
  let matches = null, rank = null, partial = 0;
  if (s.q.trim()) {
    const hits = searchCatalogMatches(searchRecords, s.q);
    matches = new Set(hits.map(h=>h.record.key)); rank = new Map(hits.map((h,i)=>[h.record.key,i]));
    partial = hits.filter(h=>h.missing.length).length;
  }
  const list = sortRecords(filterRecords(records, s, matches, saved, followed), s.sort, rank);
  lastResults = list;
  const active = ['category','topic','year','venue','source','type','tag','code','saved','followed'].filter(k=>s[k]);
  return `<section class="results"><div class="results-heading"><h1>${config.route === '' ? t('综述雷达','Survey radar') : t('综述库','Survey library')}</h1><span class="quiet" role="status">${number(list.length)} ${t('篇','surveys')} / ${number(records.length)}</span><button class="text-button" data-action="export">${t('导出 CSV ↓','Export CSV ↓')}</button></div>${active.length?`<div class="active-filters">${active.map(k=>`<button class="chip" data-clear="${k}">${e(k)}: ${e(s[k]===true?'✓':s[k])} ×</button>`).join('')}</div>`:''}${s.q?`<p class="quiet search-note">${t('搜索包括全部词匹配与部分词匹配；相关性排序优先展示全部匹配。','Search includes full and partial token matches; relevance ranks full matches first.')} ${partial ? t('候选中有部分匹配。','Partial matches are present in the candidates.') : ''}</p>`:''}${list.length ? list.slice(0,limit).map(row).join('') : `<div class="empty"><h2>${t('没有符合条件的综述','No matching surveys')}</h2><p>${t('试试更宽泛的关键词或减少筛选条件。','Try broader keywords or fewer filters.')}</p><button data-action="reset">${t('重置筛选','Reset filters')}</button></div>`}${list.length>limit?`<button class="load-more" data-action="more">${t('加载更多','Load more')} (${Math.min(limit,list.length)} / ${list.length})</button>`:''}<p class="quiet footnote">${t('引用来自 OpenAlex；括号内 ★ 为 Code 仓库的 GitHub Stars。N/A 表示未获取，不等于 0。','Citations: OpenAlex. Parenthesized ★: GitHub stars for the Code repository. N/A means unavailable, not zero.')} ${e(summary.metrics_updated_at.slice(0,10))}.</p></section>`;
}
function briefing() {
  return `<aside class="briefing"><section class="soft-panel"><h2>${t('订阅你的研究方向','Follow your research directions')}</h2><p>${t('关注分类，在综述库中只看感兴趣的方向。收藏与关注保存在当前浏览器。','Follow categories and filter your library. Saved items and follows stay in this browser.')}</p><a class="primary-button" href="${url('library/')}?followed=1">${t('我的方向','My directions')} (${followed.length}) →</a> <a href="${url('feed.xml')}">RSS ↗</a></section><section class="soft-panel"><h2>${t('目录简报','Catalog briefing')}</h2><div class="brief-stat"><strong>${number(summary.total)}</strong><span>${t('篇已收录综述','included surveys')}</span></div><div class="brief-stat"><strong>${summary.categories}</strong><span>${t('个主分类 · 多维标签','main categories · multiple tag dimensions')}</span></div><p>${t('收录范围覆盖学习方法、语言、视觉、智能体、机器人、安全、系统与领域应用。每篇作品归入一个主分类，通过标签交叉检索。','Explore learning, language, vision, agents, robotics, safety, systems and applications. Each work has one main category with cross-cutting tags.')}</p><a href="${url('landscape/')}">${t('打开主题地图 →','Open the landscape →')}</a></section><section class="soft-panel"><h2>${t('来源与覆盖状态','Source & coverage status')}</h2><p>${t('数据截止','Data through')} <strong>${summary.as_of}</strong></p><p>${number(summary.citations_available)} / ${number(summary.total)} ${t('篇有引用数','with citations')}<br>${summary.pending} ${t('组外部候选待复核','external candidate groups pending')}</p><p>${t('TechRxiv 与 Preprints.org 的网站访问受限；HF Daily Papers 是 arXiv 精选索引。平台覆盖并非全量保证。','TechRxiv and Preprints.org website access is restricted. HF Daily Papers is a selected arXiv index. Exhaustiveness is not guaranteed.')}</p><a href="${url('about/')}">${t('查看审计与限制 →','Read the audit & limitations →')}</a></section></aside>`;
}
function renderLibrary() {
  const s = state();
  app.innerHTML = `${config.route === '' ? `<section class="intro compact"><p class="eyebrow">AWESOME AI SURVEYS</p><h1>${t('让研究全景，触手可及。','Keep the research landscape in view.')}</h1><p>${t('一个主分类，多维标签。发现、比较和追踪 AI 综述。','One main category, many perspectives. Discover, compare and follow AI surveys.')}</p></section>`:''}${searchAndSort(s)}${filterPanel(s)}<div class="library-utilities"><label class="check"><input type="checkbox" data-param="saved" ${s.saved?'checked':''}> ${t('我的收藏','Saved')} (${saved.length})</label><label class="check"><input type="checkbox" data-param="followed" ${s.followed?'checked':''}> ${t('我的方向','My directions')} (${followed.length})</label><a href="${url('compare/')}">${t('对比清单','Compare list')} (${compared.length}/4) ⇄</a><span class="quiet">${t('统计快照','Metrics snapshot')}: ${summary.metrics_updated_at.slice(0,10)}</span></div><div class="${config.route === '' ? 'overview-grid':'library-grid'}">${config.route === '' ? results(s)+briefing() : categorySidebar(s)+results(s)}</div>`;
}
function barChart(entries, max, href) {
  return `<div class="bar-chart">${entries.map(([label,count,id])=>`<div class="bar-row"><a href="${href(id||label)}">${e(label)}</a><div class="bar-track"><span style="width:${Math.max(0,Math.min(100,count/max*100))}%"></span></div><strong>${number(count)}</strong></div>`).join('')}</div>`;
}
function group(key) { const m = new Map(); records.forEach(p=>m.set(p[key]||'N/A',(m.get(p[key]||'N/A')||0)+1)); return [...m.entries()]; }
function pageIntro(kicker, title, text) { return `<section class="intro"><p class="eyebrow">${kicker}</p><h1>${title}</h1><p>${text}</p></section>`; }
function renderTrends() {
  const years = group('year').sort((a,b)=>b[0]-a[0]);
  app.innerHTML = pageIntro('PUBLICATION LANDSCAPE',t('综述发表趋势','Survey publication trends'),t('统计当前目录中每个发表年份的作品数。不是 AI 全领域的发表总量，也不是引用增长曲线。','Counts by publication year in this catalog. These are not totals for the entire AI field or citation growth.')) + `<section class="panel"><h2>${t('按年份','By year')}</h2>${barChart(years,Math.max(...years.map(v=>v[1])),v=>url('library/')+'?year='+encodeURIComponent(v))}</section><div class="two-panels"><section class="soft-panel"><h2>${t('统计覆盖','Metric availability')}</h2><p>${number(summary.citations_available)} / ${number(summary.total)} ${t('篇有 OpenAlex 引用数','with OpenAlex citation counts')}</p><p>${number(summary.stars_available)} ${t('篇有 GitHub Stars','with GitHub stars')}</p><p class="quiet">${t('现有数据只有一次统计快照，无法计算引用增速。','Only one metric snapshot is available; citation growth cannot be calculated.')}</p></section><section class="soft-panel"><h2>${t('时间的含义','What the dates mean')}</h2><p>${t('发表年份沿用源记录。时间排序在同年内优先使用已提供的源提交日期；缺少精确日期时只显示年份。2026 年数据截止 11 月 8 日。','Years follow source metadata. Newest sorting uses supplied submission dates within each displayed year; records without an exact date show the year only. The 2026 snapshot ends on November 8.')}</p></section></div>`;
}
function renderCoverage() {
  const verified = records.filter(p=>p.coverage);
  app.innerHTML = pageIntro('LITERATURE COVERAGE',t('综述读到了哪一天？','How recent is the literature covered?'),t('论文发表日期与综述所覆盖文献的截止时间是两个不同字段。只有明确核验的截止时间才用于这里。','Publication date and literature coverage cutoff are separate fields. Only verified coverage dates are used here.')) + `<section class="soft-panel coverage-empty"><span class="large-number">${verified.length} / ${records.length}</span><h2>${t('篇有已核验的文献覆盖截止时间','with verified literature coverage dates')}</h2><p>${t('当前数据尚未提供这一字段。不能用发表日期推断综述已覆盖同日的所有文献；后续需要逐篇阅读正文或作者声明补齐。','This field is not available in the current data. Publication dates cannot establish literature coverage; full-text review or an author statement is needed.')}</p><a class="primary-button" href="${repo}/issues/new">${t('贡献覆盖日期与正文依据 ↗','Contribute coverage dates & evidence ↗')}</a></section>${verified.length?verified.map(row).join(''):`<section class="panel"><h2>${t('可以先按发表时间查找','Browse by publication date')}</h2><p>${t('这个入口只改变综述库的排序，不代表文献覆盖范围。','This changes the library sort order; it does not establish literature coverage.')}</p><a href="${url('library/')}?sort=time">${t('查看近期发表的综述 →','Browse recently published surveys →')}</a></section>`}`;
}
function renderLandscape() {
  const counts = new Map(group('category'));
  const tags = new Map(); records.forEach(p=>Object.values(p.tags).flat().forEach(tag=>tags.set(tag,(tags.get(tag)||0)+1)));
  const topTags = [...tags.entries()].sort((a,b)=>b[1]-a[1]).slice(0,30);
  app.innerHTML = pageIntro('RESEARCH LANDSCAPE',t('一个主分类，多种发现路径。','One category, many ways to explore.'),t('17 个主分类形成目录骨架；二级主题与方法、任务、模态、领域等标签连接跨学科作品。','17 main categories organize the catalog. Subtopics and tags connect methods, tasks, modalities and applications.'))+`<div class="landscape-grid">${taxonomy.map(c=>`<section class="panel landscape-card"><div class="card-number">${c.id.slice(0,2)}</div><h2><a href="${url('library/')}?category=${c.id}">${e(categoryName(c.id))}</a></h2><p class="quiet">${number(counts.get(c.id)||0)} ${t('篇综述','surveys')}</p><div class="topic-links">${c.topics.map(topic=>`<a href="${url('library/')}?category=${c.id}&topic=${topic.id}">${e(lang==='zh'?topic.name_zh:topic.name)}</a>`).join('')}</div><div class="card-bottom"><button data-follow="${c.id}" aria-pressed="${followed.includes(c.id)}">${followed.includes(c.id)?'✓':'＋'} ${t('关注方向','Follow')}</button><a href="${url('feeds/'+c.id+'.xml')}">RSS ↗</a></div></section>`).join('')}</div><section class="panel"><h2>${t('高频标签','Frequent tags')}</h2><p class="quiet">${t('标签来自标题线索；不同标签间会重复计数。','Tags use title cues; one work can contribute to multiple tags.')}</p><div class="chips">${topTags.map(([tag,n])=>`<a class="chip" href="${url('library/')}?tag=${encodeURIComponent(tag)}">${e(tag)} <b>${n}</b></a>`).join('')}</div></section>`;
}
function renderCompare() {
  const ids = new URLSearchParams(location.search).get('ids');
  const selected = ids !== null ? ids.split(',').slice(0,4) : compared;
  const papers = selected.map(id=>records.find(p=>p.id===id)).filter(Boolean);
  const fields = [[t('标题','Title'),p=>`<a href="${url('papers/'+p.id+'/')}">${e(p.title)}</a>`],[t('主分类','Category'),p=>e(categoryName(p.category))],[t('二级主题','Subtopic'),p=>e(topicName(p))],[t('作者','Authors'),p=>e(p.authors.join(', '))],[t('年份 / 源日期','Year / source date'),p=>e(p.date||p.year)],[t('渠道','Venue'),p=>e(p.venue)],[t('标签','Tags'),p=>e(Object.values(p.tags).flat().join(' · '))],['Paper',p=>link(p.paper_url,'Paper ↗')||'N/A'],['Code',p=>link(p.code_url,'Code ↗')||'N/A'],[t('引用 (★ Stars)','Citations (★ Stars)'),p=>metric(p)],[t('文献覆盖截止','Literature coverage'),p=>e(p.coverage||t('未核验','Not verified'))],[t('数据来源','Sources'),p=>e(p.sources.join(', '))]];
  app.innerHTML = pageIntro('SIDE BY SIDE',t('找到适合你的那篇综述。','Find the survey that fits your question.'),t('最多对比 4 篇的主题、年份与来源。这里展示元数据，不提供论文质量评分。','Compare up to four surveys by scope, date and sources. This is metadata comparison without a paper quality score.'))+`<div class="page-actions"><a class="primary-button" href="${url('library/')}">${t('从综述库添加','Add from the library')} →</a>${papers.length?`<button data-action="share-compare">${t('复制对比链接','Copy comparison link')}</button><button data-action="clear-compare">${t('清空清单','Clear list')}</button>`:''}</div>${papers.length?`<div class="table-scroll"><table class="compare-table"><thead><tr><th>${t('字段','Field')}</th>${papers.map(p=>`<th>${e(p.year)} <button data-remove="${p.id}">${t('移除','Remove')} ×</button></th>`).join('')}</tr></thead><tbody>${fields.map(([label,get])=>`<tr><th scope="row">${label}</th>${papers.map(p=>`<td>${get(p)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:`<section class="empty"><h2>${t('对比清单为空','Your comparison list is empty')}</h2><p>${t('在每条综述的下方点击「＋ 对比」。','Use “＋ Compare” under any survey to add it here.')}</p></section>`}`;
}
function renderUpdates() {
  app.innerHTML = pageIntro('CATALOG UPDATES',t('目录更新记录','Catalog updates'),t('记录数据快照与批量导入事件。导入时间不代表论文发表时间。','Catalog snapshots and import events. An import date is not a paper publication date.'))+`<div class="timeline"><section class="panel"><p class="eyebrow">${summary.as_of} · SNAPSHOT</p><h2>${t('2026 外部来源补充与引用统计','2026 source expansion & citation snapshot')}</h2><p>${t('本轮目录净新增','Net new works in this expansion')}: <strong>${summary.added}</strong></p><p>${number(summary.total)} ${t('篇收录 ·','included ·')} ${summary.pending} ${t('组外部候选待复核','external candidate groups pending')}</p><a href="${repo}/blob/main/docs/EXPANSION_2026.md">${t('查看补充报告 ↗','Read the expansion report ↗')}</a></section><section class="soft-panel"><h2>RSS</h2><p>${t('订阅目录快照更新；每个研究方向也有独立订阅源。当前订阅源包含真实的目录快照事件，不把历史论文伪装成今日新增。','Subscribe to catalog snapshot updates, or follow individual category feeds. Feeds contain actual snapshot events rather than presenting historical papers as new today.')}</p><a href="${url('feed.xml')}">${t('全站 RSS ↗','All updates RSS ↗')}</a> · <a href="${url('landscape/')}">${t('按方向订阅 →','Category feeds →')}</a></section></div>`;
}
function renderAbout() {
  app.innerHTML = pageIntro('METHOD, SOURCES & LIMITS',t('让每条记录都有据可查。','Trace every record to its source.'),t('Survey Radar 是 Awesome AI Surveys 的网站。它帮助发现综述，数据仍需要持续复核与补充。','Survey Radar is the website for Awesome AI Surveys. It helps discover reviews while keeping screening and coverage limits visible.'))+`<div class="about-grid"><section class="panel"><h2>${t('收录与分类','Inclusion & classification')}</h2><p>${t('当前收录基于元数据规则筛选的 AI 综述、文献回顾与研究全景。每篇作品只放入一个主分类，二级主题和多维标签用于交叉浏览。标题线索不能替代逐篇全文审读，也不构成同行评审认证。','AI surveys, literature reviews and research overviews screened using metadata rules. Each work has one main category, with subtopics and cross-cutting tags. Title cues do not replace full-text review or establish peer review.')}</p><p>${t('引用来自 OpenAlex；Code 后紧邻引用列，括号内为相应 GitHub 仓库 Stars。N/A 表示未匹配或获取失败，不等于 0。统计是快照，不保证实时。','Citations come from OpenAlex and appear after Code, with GitHub stars in parentheses. N/A means unmatched or unavailable, not zero. Metrics are snapshots, not live counts.')}</p><p>${t('目录不包含完整摘要，无法仅凭标题确定文献覆盖截止日期。该字段当前全部为未核验。','The catalog has no full abstracts. Literature coverage dates cannot be inferred from titles and are currently unverified.')}</p><a href="${repo}/blob/main/docs/METHODOLOGY.md">${t('完整方法说明 ↗','Full methodology ↗')}</a></section><section class="panel"><h2>${t('数据快照','Data snapshot')}</h2><dl class="fact-list"><div><dt>${t('数据截止','Through')}</dt><dd>${summary.as_of}</dd></div><div><dt>${t('收录作品','Included')}</dt><dd>${number(summary.total)}</dd></div><div><dt>${t('外部发现记录（含非综述与版本）','External discovery records, including non-surveys and versions')}</dt><dd>${number(summary.discovered)}</dd></div><div><dt>${t('待复核候选组','Pending candidate groups')}</dt><dd>${summary.pending}</dd></div></dl><a href="${repo}/blob/main/docs/EXTERNAL_PENDING_2026.md">${t('查看待复核队列 ↗','Open pending queue ↗')}</a></section></div><section class="panel"><h2>${t('来源状态与已知缺口','Source status & known gaps')}</h2><div class="table-scroll"><table><thead><tr><th>${t('来源','Source')}</th><th>${t('获取方式与限制','Access & limitations')}</th></tr></thead><tbody><tr><th>PaperVault</th><td>${t('本地会议、期刊记录及 2024—2026 年 arXiv 快照；详情页保留源文件和记录行号。','Local conference/journal records and 2024–2026 arXiv snapshots. Detail pages retain dataset and source-line provenance.')}</td></tr><tr><th>TechRxiv</th><td>${t('Crossref 登记接口与 DataCite 交叉核对。4 月至 11 月 8 日登记查询为零，网站 / sitemap 返回 HTTP 403，不能据此认定没有论文。','Crossref with a DataCite crosscheck. Registry queries for April through November 8 returned zero; website/sitemap returned HTTP 403. This does not establish absence of papers.')}</td></tr><tr><th>Preprints.org</th><td>${t('通过公开登记接口发现；直接网站访问 HTTP 403，仍存在网站层面的覆盖缺口。','Discovered through public registry APIs. Direct website access returned HTTP 403; website-level coverage remains incomplete.')}</td></tr><tr><th>HF Daily Papers</th><td>${t('官方日期 / 月份接口。它是 arXiv 精选索引，不是独立预印本托管平台，也不覆盖所有 arXiv 论文。','Official day/month APIs. A selected arXiv index, not an independent preprint host or a complete arXiv feed.')}</td></tr></tbody></table></div><p>${t('公开接口在审计范围内遍历完成，不保证平台全量或“一篇不漏”。待复核候选没有混入已收录列表。','Enumerating audited API scopes does not guarantee exhaustive platform coverage. Pending candidates remain separate from included works.')}</p><a href="${repo}/blob/main/docs/EXPANSION_2026.md">${t('覆盖审计报告 ↗','Coverage audit ↗')}</a></section><section class="panel"><h2>${t('下载、贡献与许可','Downloads, contributions & licenses')}</h2><div class="page-actions"><a href="${url('data/surveys.jsonl')}">JSONL ↓</a><a href="${url('data/metrics.json')}">Metrics JSON ↓</a><a href="${url('data/manifest.json')}">Source manifest ↓</a><a href="${repo}/issues/new">${t('提交补充或更正 ↗','Suggest an addition or correction ↗')}</a></div><p>${t('本站前端基于 Benchmark Radar 的 AGPL-3.0 代码与视觉结构改编，完整修改源码公开。原目录、论文及代码链接保留各自的许可。','The frontend adapts Benchmark Radar’s AGPL-3.0 code and visual structure. Complete modified source is public. The catalog, papers and linked repositories retain their respective licenses.')}</p><a href="${url('UPSTREAM.md')}">${t('改编说明与许可证 →','Attribution & license →')}</a><p class="quiet">${t('收藏、关注及对比清单只存储在本机浏览器；本站不使用账户或第三方分析跟踪。','Saved items, follows and comparisons are stored in this browser. No accounts or third-party analytics are used.')}</p></section>`;
}
function renderDetail() {
  const p = records.find(v=>v.id === config.paperId); if (!p) return;
  document.getElementById('detail-actions').innerHTML = `<button data-save="${p.id}" aria-pressed="${saved.includes(p.id)}">${saved.includes(p.id)?'★':'☆'} ${t('收藏','Save')}</button><button data-compare="${p.id}" aria-pressed="${compared.includes(p.id)}">${compared.includes(p.id)?'✓':'＋'} ${t('对比','Compare')}</button><a href="${url('compare/')}">${t('打开对比清单','Open comparison list')} (${compared.length}) →</a>`;
  const related = sortRecords(records.filter(v=>v.id!==p.id && v.category===p.category && v.topic===p.topic),'citations').slice(0,5);
  document.getElementById('related').innerHTML = `<h2>${t('同主题综述','Related surveys')}</h2>${related.map(row).join('')}`;
}
function render() {
  translate();
  if (!records) return;
  if (config.paperId) return renderDetail();
  const renderers = {'':renderLibrary,library:renderLibrary,compare:renderCompare,trends:renderTrends,coverage:renderCoverage,landscape:renderLandscape,updates:renderUpdates,about:renderAbout};
  renderers[config.route]?.();
}
document.getElementById('language').addEventListener('click',()=>{lang=lang==='zh'?'en':'zh';persist('language',lang);render();});
window.addEventListener('popstate',()=>{limit=30;render();});
let searchTimer;
document.addEventListener('input',event=>{
  if (event.target.id !== 'search') return;
  const input = event.target, value=input.value, caret=input.selectionStart;
  clearTimeout(searchTimer); searchTimer=setTimeout(()=>{ update({q:value,sort:value?'relevance':'time'},true); const next=document.getElementById('search');next.focus();try{next.setSelectionRange(caret,caret);}catch{} },220);
});
document.addEventListener('change',event=>{const target=event.target;if(target.dataset.param){const patch={[target.dataset.param]:target.type==='checkbox'?target.checked:target.value};if(target.dataset.param==='category')patch.topic='';update(patch);}});
document.addEventListener('keydown',event=>{if(event.key==='/' && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){const input=document.getElementById('search');if(input){event.preventDefault();input.focus();}}});
document.addEventListener('click',async event=>{
  const target=event.target.closest('button'); if(!target || !records)return;
  if(target.dataset.save){const id=target.dataset.save;saved=saved.includes(id)?saved.filter(v=>v!==id):[...saved,id];persist('saved',saved);render();}
  if(target.dataset.follow){const id=target.dataset.follow;followed=followed.includes(id)?followed.filter(v=>v!==id):[...followed,id];persist('followed',followed);render();}
  if(target.dataset.compare){const id=target.dataset.compare;if(compared.includes(id))compared=compared.filter(v=>v!==id);else if(compared.length<4)compared.push(id);else return toast(t('最多同时对比 4 篇。','Compare up to four surveys.'));persist('compare',compared);render();}
  if(target.hasAttribute('data-category'))update({category:target.dataset.category,topic:''});
  if(target.dataset.clear)update({[target.dataset.clear]:'',...(target.dataset.clear==='category'?{topic:''}:{})});
  if(target.dataset.remove){const params=new URLSearchParams(location.search);if(params.has('ids')){const ids=params.get('ids').split(',').filter(v=>v!==target.dataset.remove);update({ids:ids.join(',')});}else{compared=compared.filter(v=>v!==target.dataset.remove);persist('compare',compared);render();}}
  switch(target.dataset.action){
    case 'filters': filtersOpen=!filtersOpen;render();break;
    case 'more': {const scroll=scrollY;limit+=30;render();window.scrollTo(0,scroll);break;}
    case 'reset': history.pushState({},'',location.pathname);limit=30;render();break;
    case 'clear-compare': compared=[];persist('compare',compared);update({ids:''});break;
    case 'share-compare': {
      const ids=new URLSearchParams(location.search).get('ids')||compared.join(',');
      const value=location.origin+url('compare/')+'?ids='+encodeURIComponent(ids);
      try{await navigator.clipboard.writeText(value);toast(t('对比链接已复制','Comparison link copied'));}catch{update({ids});toast(t('链接已写入地址栏，可直接复制。','Copy the comparison URL from the address bar.'));}break;
    }
    case 'export': {
      const fields=['id','title','year','date','venue','category','topic','paper_url','code_url','citations','stars','coverage'];
      const content='\ufeff'+[fields.map(csvCell).join(','),...lastResults.map(p=>fields.map(k=>csvCell(p[k])).join(','))].join('\r\n');
      const object=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=object;a.download='survey-radar.csv';a.click();setTimeout(()=>URL.revokeObjectURL(object),1000);break;
    }
  }
});
translate();
async function load() {
  try {
    const response=await fetch(url('data/catalog.json'));
    if(!response.ok)throw new Error('HTTP '+response.status);
    catalog=await response.json();records=catalog.records;taxonomy=catalog.taxonomy;summary=catalog.summary;
    if(!Array.isArray(records)||!Array.isArray(taxonomy)||!summary)throw new Error('Invalid catalog');
    categoryMap=new Map(taxonomy.map(c=>[c.id,c]));
    searchRecords=records.map(p=>({key:p.id,name:p.title,aliases:p.authors,description:[...p.authors,topicName(p),...Object.values(p.tags).flat()].join(' '),categories:[categoryMap.get(p.category)?.name,categoryMap.get(p.category)?.name_zh,...(categoryMap.get(p.category)?.topics.filter(v=>v.id===p.topic).flatMap(v=>[v.name,v.name_zh])||[])],publisher:p.venue,modality:p.tags.modalities||[],languages:[],source:p.sources,released:p.date||String(p.year),has_paper:!!p.paper_url,has_repo:!!p.code_url}));
    saved=saved.filter(id=>records.some(p=>p.id===id));compared=compared.filter(id=>records.some(p=>p.id===id));
    render();
  } catch(error) {
    const node=app||document.getElementById('related');
    if(node)node.innerHTML=`<section class="empty" role="alert"><h1>${t('目录加载失败','Catalog could not be loaded')}</h1><p>${t('请检查网络并重试。也可以直接浏览 GitHub 上的完整目录。','Check your connection and retry, or browse the complete GitHub catalog.')}</p><button id="retry">${t('重新加载','Retry')}</button> <a href="${repo}">GitHub ↗</a><p class="quiet">${e(error.message)}</p></section>`;
    document.getElementById('retry')?.addEventListener('click',load,{once:true});
  }
}
load();
