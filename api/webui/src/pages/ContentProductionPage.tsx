import React from "react";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BookOpenText,
  Bot,
  CheckCheck,
  ChevronDown,
  CircleHelp,
  Clock3,
  FileOutput,
  FilePenLine,
  History,
  ImagePlus,
  Info,
  MessageSquareQuote,
  PencilLine,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Tags,
  WandSparkles,
} from "lucide-react";
import { Button, Card, CardDescription, CardHeader, CardTitle } from "../components/ui";

type PlatformKey = "xhs" | "douyin" | "video";
type RiskLevel = "high" | "medium" | "low";

type RiskItem = {
  id: string;
  level: RiskLevel;
  label: string;
  original: string;
  suggestion: string;
  replacement: string;
};

const PLATFORM_OPTIONS: Array<{ key: PlatformKey; label: string; short: string }> = [
  { key: "xhs", label: "小红书", short: "红" },
  { key: "douyin", label: "抖音", short: "抖" },
  { key: "video", label: "视频号", short: "视" },
];

const PLATFORM_TIPS: Record<
  PlatformKey,
  {
    title: string;
    notes: string[];
    ctas: string[];
    titlePlaceholder: string;
  }
> = {
  xhs: {
    title: "小红书建议",
    notes: [
      "封面建议使用“对比图 + 大字标题”结构，突出新手避坑收益。",
      "正文前 5 行尽量给结论，再解释原因，避免铺垫过长。",
      "标签更适合组合“猫粮推荐 / 新手养猫 / 避坑攻略”这种搜索型词组。",
    ],
    ctas: ["点击看看原图", "有什么问题评论区问我", "收藏这篇，下次不纠结"],
    titlePlaceholder: "养猫避坑避坑指南｜新手必看的 6 个选粮标准",
  },
  douyin: {
    title: "抖音建议",
    notes: [
      "前 3 秒直接抛出冲突：为什么你买的猫粮贵但不一定合适。",
      "分句更短，适合口播转字幕，建议每行控制在 10 到 14 个字。",
      "结尾最好留一个动作指令，比如评论关键词领取选粮清单。",
    ],
    ctas: ["评论区回你清单", "先点赞再看下一条", "想看第二期扣 1"],
    titlePlaceholder: "新手买猫粮最容易踩的 3 个坑，第一条很多人都中招",
  },
  video: {
    title: "视频号建议",
    notes: [
      "更适合“经验总结 + 信任背书”的表达，不要太像广告投放文案。",
      "推荐加入一句身份线索，例如“这是我养猫 4 年总结出来的标准”。",
      "按钮型 CTA 可以弱一点，改成咨询式表达更自然。",
    ],
    ctas: ["需要完整清单可以留言", "想看配料表拆解告诉我", "转给正在养猫的朋友"],
    titlePlaceholder: "养猫 4 年后，我总结出给新手最实用的 6 条选粮标准",
  },
};

const INITIAL_TITLE = "养猫选粮避坑指南｜新手必看的 6 个选粮标准";

const INITIAL_BODY = `养猫的第一步，选对主粮真的太重要了！

市面上猫粮品牌那么多，配方五花八门，价格差距也大，新手很容易踩坑。
今天这篇超全选粮攻略，帮你避开常见误区，真正选到适合自家猫咪的好粮！

一、看配料表，前三位很关键
优质猫粮的前三位应该是肉类原料（如鸡肉、鸭肉、鱼肉等），而不是谷物或植物蛋白。
猫咪是肉食动物，动物蛋白来源更优质，营养吸收率更高。`;

const SUGGESTION_BLOCKS = [
  {
    title: "爆款开头推荐",
    items: [
      "养猫千万别乱买猫粮，这 3 个坑新手最容易中。",
      "花了几千块买猫粮，我最后才发现真正关键的是配料表。",
      "90% 新手看配料时都会忽略这一行，结果一直买错。",
    ],
  },
  {
    title: "内容结构建议",
    items: [
      "先给结论，再解释原因，降低读者流失。",
      "做成 6 条标准清单，方便收藏和二次传播。",
      "最后补一句“如何结合预算挑选”，能提升咨询转化。",
    ],
  },
  {
    title: "互动引导建议",
    items: [
      "收藏这篇留着慢慢看",
      "你家猫咪吃什么粮？",
      "评论区交流一下",
      "点击主页领取选粮清单",
    ],
  },
  {
    title: "延伸选题推荐",
    items: [
      "猫粮软便怎么选粮",
      "猫粮品牌红黑榜",
      "不同预算怎么挑粮",
      "高蛋白猫粮到底怎么选",
    ],
  },
];

const HISTORY_VERSIONS = [
  { version: "v3.2", status: "当前版本", author: "张晓彤", time: "05-22 10:24", note: "编辑中" },
  { version: "v3.1", status: "", author: "张晓彤", time: "05-22 09:41", note: "待审核" },
  { version: "v3.0", status: "", author: "李思琪", time: "05-22 08:55", note: "已拒绝" },
  { version: "v2.1", status: "", author: "李思琪", time: "05-21 18:32", note: "已通过" },
  { version: "v2.0", status: "", author: "李思琪", time: "05-21 15:11", note: "已通过" },
];

const AUDIT_LOGS = [
  { status: "success", title: "审核通过", user: "李思琪（合规专员）", time: "05-21 18:32", detail: "内容符合平台合规规范，已通过审核" },
  { status: "danger", title: "审核不通过", user: "李思琪（合规专员）", time: "05-21 17:48", detail: "存在夸大表述，请删除明显断言类用语" },
  { status: "info", title: "提交审核", user: "张晓彤（内容运营）", time: "05-21 17:10", detail: "提交版本 v3.0，等待审核" },
];

const ACTION_LOGS = [
  { time: "05-22 10:24", user: "张晓彤", detail: "修改正文内容" },
  { time: "05-22 09:41", user: "张晓彤", detail: "修改标题" },
  { time: "05-22 08:55", user: "张晓彤", detail: "添加配图" },
  { time: "05-22 08:32", user: "张晓彤", detail: "创建草稿" },
];

const REFERENCE_ASSETS = [
  { id: "ref-1", label: "配料表模板", color: "warm" },
  { id: "ref-2", label: "猫咪场景图", color: "photo" },
  { id: "ref-3", label: "标题示例图", color: "fresh" },
];

const INITIAL_RISKS: RiskItem[] = [
  {
    id: "risk-1",
    level: "high",
    label: "高风险",
    original: "这款猫粮绝对能彻底解决软便问题，见效非常快！",
    suggestion: "删除“彻底解决”等绝对化表达，改为经验描述。",
    replacement: "这款猫粮对肠胃敏感猫更友好，但仍建议结合猫咪实际状态观察。",
  },
  {
    id: "risk-2",
    level: "medium",
    label: "中风险",
    original: "最安全、最健康的猫粮选择",
    suggestion: "避免使用“最安全”等无法量化的结论型词语。",
    replacement: "更适合新手参考的常见猫粮选择标准",
  },
  {
    id: "risk-3",
    level: "low",
    label: "低风险",
    original: "性价比超高，值得入手",
    suggestion: "保留前提下，建议增加适用条件，让表达更审慎。",
    replacement: "如果预算有限，这类配方通常更值得优先比较。",
  },
];

function levelTone(level: RiskLevel) {
  if (level === "high") return "danger";
  if (level === "medium") return "warning";
  return "success";
}

export function ContentProductionPage() {
  const [platform, setPlatform] = React.useState<PlatformKey>("xhs");
  const [title, setTitle] = React.useState(INITIAL_TITLE);
  const [body, setBody] = React.useState(INITIAL_BODY);
  const [briefTitle, setBriefTitle] = React.useState("内容简报");
  const [statusMessage, setStatusMessage] = React.useState("草稿已同步到本地工作区。");
  const [collapsedRisks, setCollapsedRisks] = React.useState<string[]>([]);
  const [ignoredRisks, setIgnoredRisks] = React.useState<string[]>([]);
  const [risks, setRisks] = React.useState<RiskItem[]>(INITIAL_RISKS);

  const activeTips = PLATFORM_TIPS[platform];
  const visibleRisks = risks.filter((item) => !ignoredRisks.includes(item.id));
  const score = visibleRisks.some((item) => item.level === "high")
    ? 82
    : visibleRisks.some((item) => item.level === "medium")
      ? 91
      : 98;
  const titleLimit = platform === "xhs" ? 30 : platform === "douyin" ? 24 : 28;

  const metricCards = [
    { label: "待审核内容", value: "24", delta: "较昨日 ↑ 8", tone: "neutral", icon: <FilePenLine size={16} /> },
    { label: "高风险草稿", value: "5", delta: "较昨日 ↑ 2", tone: "danger", icon: <ShieldAlert size={16} /> },
    { label: "今日通过率", value: "86%", delta: "较昨日 ↑ 6%", tone: "success", icon: <BadgeCheck size={16} /> },
    { label: "平均修改次数", value: "1.6 次", delta: "较昨日 ↓ 0.2", tone: "info", icon: <PencilLine size={16} /> },
  ];

  function updateStatus(message: string) {
    setStatusMessage(message);
  }

  function insertText(snippet: string) {
    setBody((current) => `${current}\n\n${snippet}`);
    updateStatus("已将建议内容追加到正文。");
  }

  function replaceRiskText(risk: RiskItem) {
    setBody((current) => (current.includes(risk.original) ? current.replace(risk.original, risk.replacement) : `${current}\n\n${risk.replacement}`));
    setRisks((current) => current.filter((item) => item.id !== risk.id));
    updateStatus(`已替换 ${risk.label} 提示内容。`);
  }

  function ignoreRisk(id: string) {
    setIgnoredRisks((current) => [...current, id]);
    updateStatus("该条风险提示已忽略。");
  }

  function toggleRisk(id: string) {
    setCollapsedRisks((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  function resetDraft() {
    setTitle(activeTips.titlePlaceholder);
    setBody(INITIAL_BODY);
    setRisks(INITIAL_RISKS);
    setIgnoredRisks([]);
    setCollapsedRisks([]);
    updateStatus("已根据当前平台建议重置草稿内容。");
  }

  return (
    <section className="cp-page">
      <div className="cp-topbar">
        <div className="cp-topbar__title">
          <div className="cp-topbar__icon">
            <BookOpenText size={18} />
          </div>
          <div>
            <span>内容工作台</span>
            <h1>内容生产与合规审核</h1>
          </div>
        </div>

        <div className="cp-topbar__search">
          <Search size={16} />
          <input type="text" placeholder="搜索项目、关键词、话题、账号..." />
        </div>

        <div className="cp-topbar__actions">
          <button type="button" className="cp-topbar__ghost">
            <Sparkles size={15} />
            AI 助手
          </button>
          <button type="button" className="cp-topbar__ghost">
            <CircleHelp size={15} />
            帮助
          </button>
        </div>
      </div>

      <div className="cp-metrics">
        {metricCards.map((item) => (
          <article key={item.label} className={`cp-metric-card is-${item.tone}`}>
            <div>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <small>{item.delta}</small>
            </div>
            <i>{item.icon}</i>
          </article>
        ))}
      </div>

      <div className="cp-layout">
        <div className="cp-main">
          <Card className="cp-panel cp-editor-shell">
            <div className="cp-editor-head">
              <div className="cp-platforms">
                <span className="cp-section-label">平台</span>
                {PLATFORM_OPTIONS.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    className={`cp-platform-chip ${platform === item.key ? "is-active" : ""}`}
                    onClick={() => {
                      setPlatform(item.key);
                      setTitle(PLATFORM_TIPS[item.key].titlePlaceholder);
                      updateStatus(`已切换到 ${item.label} 内容模版。`);
                    }}
                  >
                    <b>{item.short}</b>
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>

              <div className="cp-editor-head__tools">
                <button type="button" className="cp-inline-link" onClick={resetDraft}>
                  <RefreshCw size={14} />
                  重置草稿
                </button>
              </div>
            </div>

            <label className="cp-field">
              <span>标题</span>
              <div className="cp-title-wrap">
                <input value={title} onChange={(event) => setTitle(event.target.value)} />
                <small>{title.length}/{titleLimit}</small>
              </div>
            </label>

            <div className="cp-field">
              <div className="cp-field__row">
                <span>正文</span>
                <button type="button" className="cp-inline-link" onClick={() => insertText("如果你想看不同预算怎么选粮，我下一篇继续拆。")}>
                  <WandSparkles size={14} />
                  AI 改写
                </button>
              </div>

              <div className="cp-editor-toolbar">
                {["↶", "↷", "B", "I", "U", "S", "H1", "H2", "≡", "☰", "❝", "🖼"].map((tool) => (
                  <button key={tool} type="button">{tool}</button>
                ))}
              </div>

              <textarea value={body} onChange={(event) => setBody(event.target.value)} rows={14} />

              <div className="cp-editor-footer">
                <span>字数：{body.length}</span>
                <span>预计阅读时长：2 分 10 秒</span>
              </div>
            </div>
          </Card>

          <Card className="cp-panel cp-ai-assistant">
            <div className="cp-ai-assistant__title">
              <div>
                <span className="cp-section-label">AI 写作助手</span>
                <h3>给当前草稿的结构、互动和延伸建议</h3>
              </div>
              <Bot size={18} />
            </div>

            <div className="cp-suggestion-grid">
              {SUGGESTION_BLOCKS.map((block) => (
                <section key={block.title} className="cp-suggestion-card">
                  <strong>{block.title}</strong>
                  <div className="cp-suggestion-list">
                    {block.items.map((item) => (
                      <button key={item} type="button" onClick={() => insertText(item)}>
                        {item}
                      </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </Card>

          <div className="cp-bottom-grid">
            <Card className="cp-panel">
              <div className="cp-subpanel-title">
                <div>
                  <span className="cp-section-label">历史版本</span>
                  <h3>版本演进</h3>
                </div>
                <History size={16} />
              </div>
              <div className="cp-log-list">
                {HISTORY_VERSIONS.map((item) => (
                  <div key={`${item.version}-${item.time}`} className="cp-log-row">
                    <div className="cp-log-main">
                      <strong>{item.version}</strong>
                      {item.status ? <span className="cp-status-pill is-current">{item.status}</span> : null}
                    </div>
                    <span>{item.author}</span>
                    <span>{item.time}</span>
                    <em>{item.note}</em>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="cp-panel">
              <div className="cp-subpanel-title">
                <div>
                  <span className="cp-section-label">审核记录</span>
                  <h3>流程状态</h3>
                </div>
                <CheckCheck size={16} />
              </div>
              <div className="cp-audit-list">
                {AUDIT_LOGS.map((item) => (
                  <article key={`${item.title}-${item.time}`} className={`cp-audit-item is-${item.status}`}>
                    <div className="cp-audit-item__head">
                      <strong>{item.title}</strong>
                      <span>{item.time}</span>
                    </div>
                    <p>{item.detail}</p>
                    <small>{item.user}</small>
                  </article>
                ))}
              </div>
            </Card>

            <Card className="cp-panel">
              <div className="cp-subpanel-title">
                <div>
                  <span className="cp-section-label">操作记录</span>
                  <h3>最近编辑</h3>
                </div>
                <Clock3 size={16} />
              </div>
              <div className="cp-action-list">
                {ACTION_LOGS.map((item) => (
                  <div key={`${item.time}-${item.detail}`} className="cp-action-row">
                    <span>{item.time}</span>
                    <strong>{item.user}</strong>
                    <p>{item.detail}</p>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>

        <aside className="cp-side">
          <Card className="cp-panel cp-score-panel">
            <div className="cp-score-panel__head">
              <div>
                <span className="cp-section-label">合规审核</span>
                <h3>内容风险评分</h3>
              </div>
              <button type="button" className="cp-inline-link" onClick={() => updateStatus("已重新检测当前草稿。")}>
                <RefreshCw size={14} />
                重新检测
              </button>
            </div>

            <div className="cp-score-panel__body">
              <div className="cp-score-badge">
                <span>风险评分</span>
                <strong>{score}</strong>
                <em>{score >= 90 ? "低风险" : score >= 85 ? "通过" : "中风险"}</em>
              </div>

              <div className="cp-score-breakdown">
                <div><span>高风险</span><strong>{visibleRisks.filter((item) => item.level === "high").length}</strong></div>
                <div><span>中风险</span><strong>{visibleRisks.filter((item) => item.level === "medium").length}</strong></div>
                <div><span>低风险</span><strong>{visibleRisks.filter((item) => item.level === "low").length}</strong></div>
                <div><span>提示</span><strong>2</strong></div>
              </div>
            </div>
          </Card>

          <Card className="cp-panel">
            <div className="cp-subpanel-title">
              <div>
                <span className="cp-section-label">敏感词检测</span>
                <h3>{visibleRisks.length} 条待处理</h3>
              </div>
              <button type="button" className="cp-collapse-link">
                收起
                <ChevronDown size={14} />
              </button>
            </div>

            <div className="cp-risk-list">
              {visibleRisks.map((risk) => {
                const collapsed = collapsedRisks.includes(risk.id);
                return (
                  <article key={risk.id} className={`cp-risk-card is-${risk.level}`}>
                    <div className="cp-risk-card__head">
                      <span className={`cp-status-pill is-${levelTone(risk.level)}`}>{risk.label}</span>
                      <button type="button" className="cp-text-btn" onClick={() => toggleRisk(risk.id)}>
                        {collapsed ? "展开" : "收起"}
                      </button>
                    </div>
                    {!collapsed ? (
                      <>
                        <div className="cp-risk-card__body">
                          <p><strong>原文：</strong>{risk.original}</p>
                          <p><strong>建议：</strong>{risk.suggestion}</p>
                        </div>
                        <div className="cp-risk-card__actions">
                          <Button variant="primary" onClick={() => replaceRiskText(risk)}>一键替换</Button>
                          <Button variant="ghost" onClick={() => ignoreRisk(risk.id)}>忽略</Button>
                        </div>
                      </>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </Card>

          <Card className="cp-panel cp-brief-panel">
            <div className="cp-subpanel-title">
              <div>
                <span className="cp-section-label">内容简报</span>
                <h3>{briefTitle}</h3>
              </div>
              <button type="button" className="cp-inline-link" onClick={() => setBriefTitle("猫粮新手避坑指南")}>
                编辑
              </button>
            </div>

            <div className="cp-brief-items">
              <div>
                <span>主题</span>
                <strong>新手养猫选粮指南</strong>
              </div>
              <div>
                <span>目标人群</span>
                <strong>新手铲屎官 / 养猫 1 年以内</strong>
              </div>
              <div>
                <span>内容目标</span>
                <p>科普选粮要点，提升品牌信任，引导收藏与咨询。</p>
              </div>
              <div>
                <span>关键词</span>
                <div className="cp-tag-list">
                  {["猫粮推荐", "新手养猫", "选粮标准", "猫粮避坑"].map((item) => <b key={item}>{item}</b>)}
                </div>
              </div>
              <div>
                <span>参考资料</span>
                <div className="cp-reference-list">
                  {REFERENCE_ASSETS.map((item) => (
                    <div key={item.id} className={`cp-reference-thumb is-${item.color}`}>
                      <em>{item.label}</em>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          <div className="cp-side-grid">
            <Card className="cp-panel">
              <div className="cp-subpanel-title">
                <div>
                  <span className="cp-section-label">内容合规建议</span>
                  <h3>逐项检查</h3>
                </div>
                <ShieldCheck size={16} />
              </div>
              <div className="cp-check-list">
                {[
                  ["避免使用绝对化、极限化用语", "中风险"],
                  ["引用数据需明确来源或说明经验参考", "通过"],
                  ["不出现贬损或竞品比较式承诺", "通过"],
                  ["结尾引导咨询动作可执行", "通过"],
                ].map(([label, status]) => (
                  <div key={label} className="cp-check-row">
                    <span>{label}</span>
                    <strong className={status === "中风险" ? "warn" : "ok"}>{status}</strong>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="cp-panel">
              <div className="cp-subpanel-title">
                <div>
                  <span className="cp-section-label">品牌内容要求</span>
                  <h3>当前匹配</h3>
                </div>
                <Info size={16} />
              </div>
              <div className="cp-check-list">
                {[
                  "符合品牌价值观",
                  "使用品牌配色规范",
                  "露出品牌名称 / 产品",
                  "结尾引导咨询或行动",
                ].map((label) => (
                  <div key={label} className="cp-check-row">
                    <span>{label}</span>
                    <strong className="ok">通过</strong>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <Card className="cp-panel">
            <div className="cp-subpanel-title">
              <div>
                <span className="cp-section-label">平台适配建议</span>
                <h3>{activeTips.title}</h3>
              </div>
              <Tags size={16} />
            </div>
            <ul className="cp-note-list">
              {activeTips.notes.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </Card>

          <Card className="cp-panel">
            <div className="cp-subpanel-title">
              <div>
                <span className="cp-section-label">推荐 CTA 话术</span>
                <h3>适合当前平台</h3>
              </div>
              <MessageSquareQuote size={16} />
            </div>
            <div className="cp-cta-list">
              {activeTips.ctas.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => insertText(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </Card>
        </aside>
      </div>

      <div className="cp-footer-bar">
        <div className="cp-footer-bar__status">
          <AlertTriangle size={15} />
          <span>{statusMessage}</span>
        </div>
        <div className="cp-footer-bar__actions">
          <Button variant="ghost" onClick={() => updateStatus("草稿已保存。")}>保存草稿</Button>
          <Button variant="ghost" onClick={() => updateStatus("已生成 3 条封面建议。")}><ImagePlus size={15} />生成封面建议</Button>
          <Button variant="ghost" onClick={() => updateStatus("脚本导出成功。")}><FileOutput size={15} />导出脚本</Button>
          <Button variant="primary" onClick={() => updateStatus("已提交审核，等待合规专员处理。")}>
            提交审核
            <ArrowRight size={15} />
          </Button>
        </div>
      </div>
    </section>
  );
}
