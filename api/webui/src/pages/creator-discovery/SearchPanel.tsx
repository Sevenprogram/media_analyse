import React from "react";
import { Sparkles, BookmarkPlus, RotateCcw, Plus, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "../../components/ui";
import { PLATFORM_OPTIONS } from "./utils";

export type SearchPanelValue = {
  query: string;
  platforms: string[];
  followerRange: string;
  recentPostsMin: string;
  activityLevel: string;
  engagementMin: string;
  viralMin: string;
  limit: string;
  includeRealtime: boolean;
};

export const DEFAULT_SEARCH: SearchPanelValue = {
  query: "寻找宠物主粮领域的新手养猫达人",
  platforms: ["dy", "xhs", "bili", "wxchannels"],
  followerRange: "10k-500k",
  recentPostsMin: "2",
  activityLevel: "active",
  engagementMin: "0.02",
  viralMin: "0.05",
  limit: "50",
  includeRealtime: false,
};

const FOLLOWER_OPTIONS = [
  { value: "any", label: "不限" },
  { value: "1k-10k", label: "1千 - 1万" },
  { value: "10k-100k", label: "1万 - 10万" },
  { value: "10k-500k", label: "1万 - 50万" },
  { value: "100k-1m", label: "10万 - 100万" },
  { value: "1m+", label: "100万+" },
];

const RECENT_POSTS_OPTIONS = [
  { value: "0", label: "不限" },
  { value: "1", label: "≥ 1" },
  { value: "2", label: "≥ 2" },
  { value: "5", label: "≥ 5" },
  { value: "10", label: "≥ 10" },
];

const ACTIVITY_OPTIONS = [
  { value: "any", label: "不限" },
  { value: "active", label: "活跃" },
  { value: "highly", label: "高度活跃" },
  { value: "dormant", label: "沉寂" },
];

const ENGAGEMENT_OPTIONS = [
  { value: "0", label: "不限" },
  { value: "0.01", label: "≥ 1%" },
  { value: "0.02", label: "≥ 2%" },
  { value: "0.05", label: "≥ 5%" },
  { value: "0.1", label: "≥ 10%" },
];

const VIRAL_OPTIONS = [
  { value: "0", label: "不限" },
  { value: "0.02", label: "≥ 2%" },
  { value: "0.05", label: "≥ 5%" },
  { value: "0.1", label: "≥ 10%" },
  { value: "0.2", label: "≥ 20%" },
];

function PlatformChip({
  value,
  label,
  active,
  onToggle,
}: {
  value: string;
  label: string;
  active: boolean;
  onToggle: (value: string, next: boolean) => void;
}) {
  return (
    <button
      type="button"
      className={`cd-chip ${active ? "is-active" : ""}`}
      data-platform={value}
      onClick={() => onToggle(value, !active)}
    >
      <span className={`cd-chip-logo platform-${value}`} aria-hidden />
      {label}
    </button>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (next: string) => void;
}) {
  return (
    <label className="cd-filter">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function SearchPanel({
  value,
  onChange,
  onSubmit,
  onReset,
  onSave,
  searching,
}: {
  value: SearchPanelValue;
  onChange: (next: SearchPanelValue) => void;
  onSubmit: () => void;
  onReset: () => void;
  onSave: () => void;
  searching: boolean;
}) {
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const togglePlatform = (platform: string, next: boolean) => {
    onChange({
      ...value,
      platforms: next
        ? value.platforms.includes(platform)
          ? value.platforms
          : [...value.platforms, platform]
        : value.platforms.filter((item) => item !== platform),
    });
  };
  const update = (patch: Partial<SearchPanelValue>) => onChange({ ...value, ...patch });

  return (
    <div className="cd-search-card">
      <div className="cd-query-row">
        <label className="cd-query">
          <span>自然语言查询</span>
          <input
            value={value.query}
            onChange={(event) => update({ query: event.target.value })}
            placeholder="例如：寻找宠物主粮领域的新手养猫达人"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onSubmit();
              }
            }}
          />
        </label>
        <div className="cd-query-actions">
          <Button variant="primary" onClick={onSubmit} disabled={searching || !value.query.trim() || !value.platforms.length}>
            <Sparkles size={16} />
            智能发现
          </Button>
          <Button variant="ghost" onClick={onSave} type="button">
            <BookmarkPlus size={16} />
            保存搜索
          </Button>
          <Button variant="ghost" onClick={onReset} type="button">
            <RotateCcw size={16} />
            重置
          </Button>
        </div>
      </div>

      <div className="cd-platform-row">
        <span className="cd-row-label">平台</span>
        <div className="cd-chip-list">
          {PLATFORM_OPTIONS.map((option) => (
            <PlatformChip
              key={option.value}
              value={option.value}
              label={option.label}
              active={value.platforms.includes(option.value)}
              onToggle={togglePlatform}
            />
          ))}
          <button type="button" className="cd-chip cd-chip-add" disabled>
            <Plus size={14} />
            添加平台
          </button>
        </div>
      </div>

      <div className="cd-filter-row">
        <FilterSelect label="粉丝数" value={value.followerRange} options={FOLLOWER_OPTIONS} onChange={(next) => update({ followerRange: next })} />
        <FilterSelect label="近 30 天发文数" value={value.recentPostsMin} options={RECENT_POSTS_OPTIONS} onChange={(next) => update({ recentPostsMin: next })} />
        <FilterSelect label="近 30 天活跃度" value={value.activityLevel} options={ACTIVITY_OPTIONS} onChange={(next) => update({ activityLevel: next })} />
        <FilterSelect label="互动率" value={value.engagementMin} options={ENGAGEMENT_OPTIONS} onChange={(next) => update({ engagementMin: next })} />
        <FilterSelect label="爆款率" value={value.viralMin} options={VIRAL_OPTIONS} onChange={(next) => update({ viralMin: next })} />
      </div>

      <button
        type="button"
        className="cd-advanced-toggle"
        onClick={() => setAdvancedOpen((open) => !open)}
        aria-expanded={advancedOpen}
      >
        高级筛选
        {advancedOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {advancedOpen && (
        <div className="cd-advanced-row">
          <label className="cd-filter">
            <span>达人数量上限</span>
            <input
              value={value.limit}
              onChange={(event) => update({ limit: event.target.value })}
              inputMode="numeric"
            />
          </label>
          <label className="cd-filter cd-filter-toggle">
            <input
              type="checkbox"
              checked={value.includeRealtime}
              onChange={(event) => update({ includeRealtime: event.target.checked })}
            />
            <span>实时搜索小红书 / 抖音</span>
          </label>
          <span className="cd-advanced-hint">更多维度（地区、性别、内容类型）正在接入</span>
        </div>
      )}
    </div>
  );
}
