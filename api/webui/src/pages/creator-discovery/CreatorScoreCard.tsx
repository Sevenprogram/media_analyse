import React from "react";
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from "recharts";
import { X, Users, MonitorCheck, Download } from "lucide-react";
import { Button } from "../../components/ui";
import {
  UnknownRecord,
  candidateMetric,
  commerceSignals,
  creatorAvatarUrl,
  creatorDisplayName,
  creatorProfileId,
  evidencePosts,
  formatCount,
  formatScore,
  labelPlatform,
  matchBandLabel,
  matchBandOf,
  matchedKeywords,
  relatedTopics,
  scoreDimensions,
  shortTime,
  text,
  tierLabel,
  tierOf,
} from "./utils";

export function CreatorScoreCard({
  row,
  rank,
  updatedAt,
  onClose,
  onAddCandidate,
  onAddRival,
  onCreateMonitor,
  onExport,
}: {
  row: UnknownRecord;
  rank: number;
  updatedAt: string;
  onClose: () => void;
  onAddCandidate: () => void;
  onAddRival: () => void;
  onCreateMonitor: () => void;
  onExport: () => void;
}) {
  const tier = tierOf(row);
  const band = matchBandOf(row);
  const score = formatScore(row.match_score);
  const dims = scoreDimensions(row);
  const radarData = dims.map((dim) => ({ subject: dim.label, value: dim.value, fullMark: dim.max }));
  const evidence = evidencePosts(row);
  const keywords = matchedKeywords(row);
  const signals = commerceSignals(row);
  const topics = relatedTopics(row);
  const avatar = creatorAvatarUrl(row);
  const name = creatorDisplayName(row);
  const profileId = creatorProfileId(row);
  const platform = text(row.platform, "");
  const followerCount = formatCount(candidateMetric(row, "follower_count"));

  return (
    <aside className="cd-score-card" aria-label="达人评分卡">
      <header className="cd-score-card-head">
        <div>
          <span className="cd-score-card-eyebrow">达人评分卡</span>
        </div>
        <button type="button" className="cd-score-card-close" onClick={onClose} aria-label="关闭">
          <X size={16} />
        </button>
      </header>

      <div className="cd-score-card-profile">
        <div className="cd-avatar large" aria-hidden>
          {avatar ? <img src={avatar} alt="" /> : <span>{name.slice(0, 1)}</span>}
        </div>
        <div className="cd-score-card-profile-info">
          <div className="cd-score-card-name">
            <strong>{name}</strong>
            <span className="cd-tag-muted">新手养猫</span>
            <span className={`cd-tier-badge tier-${tier}`}>{tierLabel(tier)}</span>
          </div>
          <div className="cd-score-card-line">
            <span className={`cd-platform-mini platform-${platform}`}>{labelPlatform(platform)}</span>
            <span>ID: {profileId || "-"}</span>
            <span>{followerCount} 粉丝</span>
          </div>
          <p className="cd-score-card-bio">{text(row.bio || row.signature, "记录两只布偶的日常 | 新手养猫经验分享")}</p>
        </div>
      </div>

      <section className="cd-score-card-summary">
        <div>
          <span>匹配分</span>
          <small className={`cd-band band-${band}`}>{matchBandLabel(band)}</small>
        </div>
        <strong className="cd-score-card-score">
          {score}
          <em>/100</em>
        </strong>
        <ul>
          <li>
            <span>排名</span>
            <strong>{rank || "-"}</strong>
          </li>
          <li>
            <span>数据更新</span>
            <strong>{updatedAt}</strong>
          </li>
        </ul>
      </section>

      <section className="cd-score-card-block">
        <h3>评分维度</h3>
        <div className="cd-radar-row">
          <div className="cd-radar">
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData} outerRadius={70}>
                <PolarGrid stroke="#d6e7dc" />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: "#5a6a64" }} />
                <PolarRadiusAxis tick={false} axisLine={false} domain={[0, "dataMax"]} />
                <Radar dataKey="value" stroke="#15b67a" fill="#15b67a" fillOpacity={0.18} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <ul className="cd-dim-list">
            {dims.map((dim) => (
              <li key={dim.key}>
                <span>{dim.label}</span>
                <strong>{dim.value}</strong>
                <em>/{dim.max}</em>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="cd-score-card-block">
        <h3>
          代表性内容证据
          <small>（近 30 天）</small>
        </h3>
        {evidence.length ? (
          <div className="cd-evidence-grid">
            {evidence.map((post, index) => (
              <article key={index} className="cd-evidence-card">
                <div className="cd-evidence-cover" aria-hidden>
                  {post.cover ? <img src={post.cover} alt="" /> : <span>{(post.title || "").slice(0, 2) || "内容"}</span>}
                </div>
                <p>{post.title}</p>
                <div className="cd-evidence-meta">
                  <span>♥ {formatCount(post.likes)}</span>
                  <span>★ {formatCount(post.collects)}</span>
                  <span>{shortTime(post.publishedAt)}</span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="cd-empty-mini">暂无可展示的代表性内容</p>
        )}
      </section>

      <section className="cd-score-card-block">
        <h3>匹配关键词</h3>
        <div className="cd-keyword-row">
          {keywords.length ? (
            keywords.map((keyword) => (
              <span key={keyword} className="cd-keyword-chip">#{keyword}</span>
            ))
          ) : (
            <span className="cd-empty-mini">暂无命中关键词</span>
          )}
        </div>
      </section>

      <section className="cd-score-card-block">
        <h3>商业化信号</h3>
        <div className="cd-signal-grid">
          {signals.map((signal) => (
            <div key={signal.key} className="cd-signal-card">
              <span className={`cd-signal-icon signal-${signal.key}`} aria-hidden />
              <div>
                <span>{signal.label}</span>
                <strong>{signal.value}</strong>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="cd-score-card-block">
        <h3>
          关联话题
          <small>（近 30 天）</small>
          <button type="button" className="cd-link-more">更多</button>
        </h3>
        {topics.length ? (
          <ul className="cd-topic-list">
            {topics.slice(0, 5).map((topic) => (
              <li key={topic.topic}>
                <span>#{topic.topic}</span>
                <strong>{formatCount(topic.heat)}</strong>
              </li>
            ))}
          </ul>
        ) : (
          <p className="cd-empty-mini">暂未关联话题</p>
        )}
      </section>

      <footer className="cd-score-card-actions">
        <Button variant="primary" onClick={onAddCandidate}>
          加入候选池
        </Button>
        <Button variant="ghost" onClick={onAddRival}>
          <Users size={14} />
          加入友商池
        </Button>
        <Button variant="ghost" onClick={onCreateMonitor}>
          <MonitorCheck size={14} />
          创建监控
        </Button>
        <Button variant="ghost" onClick={onExport}>
          <Download size={14} />
          导出
        </Button>
      </footer>
    </aside>
  );
}
