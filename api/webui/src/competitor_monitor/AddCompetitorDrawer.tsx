import React from "react";
import { Loader2, Plus } from "lucide-react";
import { Button, Drawer } from "../components/ui";
import { api } from "../utils/api";
import type { MonitorType, WorkbenchAccount } from "./types";

export interface AddCompetitorDrawerProps {
  open: boolean;
  monitorType: MonitorType;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}

interface FormState {
  platform: string;
  profileUrl: string;
  creatorId: string;
  displayName: string;
  notes: string;
}

const INITIAL: FormState = {
  platform: "xhs",
  profileUrl: "",
  creatorId: "",
  displayName: "",
  notes: "",
};

export function AddCompetitorDrawer({ open, monitorType, onOpenChange, onCreated }: AddCompetitorDrawerProps) {
  const [form, setForm] = React.useState<FormState>(INITIAL);
  const [submitting, setSubmitting] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);
  const isCreatorMonitor = monitorType === "partner_creator";

  React.useEffect(() => {
    if (!open) {
      setMessage(null);
      setForm(INITIAL);
    }
  }, [open]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const profileUrl = form.profileUrl.trim();
    const creatorId = form.creatorId.trim();
    const displayName = form.displayName.trim();

    if (!profileUrl && !creatorId) {
      setMessage("请填写主页 URL 或账号 ID。");
      return;
    }

    setSubmitting(true);
    setMessage(null);

    try {
      let created: WorkbenchAccount;
      if (profileUrl) {
        created = await api<WorkbenchAccount>("/api/competitors/from-url", {
          method: "POST",
          body: JSON.stringify({
            platform: form.platform,
            profile_url: profileUrl,
            monitor_type: monitorType,
            display_name: displayName || undefined,
            notes: form.notes.trim() || undefined,
          }),
        });
      } else {
        created = await api<WorkbenchAccount>("/api/competitors", {
          method: "POST",
          body: JSON.stringify({
            platform: form.platform,
            creator_id: creatorId,
            monitor_type: monitorType,
            display_name: displayName || undefined,
            notes: form.notes.trim() || undefined,
            enabled: true,
          }),
        });
      }

      if (!displayName && created?.id) {
        try {
          await api(`/api/competitors/${created.id}/refresh-profile`, {
            method: "POST",
          });
        } catch {
          // Keep creation successful even if profile enrichment misses.
        }
      }

      onCreated();
      onOpenChange(false);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange} title={isCreatorMonitor ? "新增达人监控" : "新增友商"}>
      <form className="cmw-add-form" onSubmit={handleSubmit}>
        <p className="cmw-add-form__hint">
          {isCreatorMonitor
            ? "优先粘贴合作达人的小红书或抖音主页 URL；如果已经知道账号 ID，也可以直接录入。"
            : "优先粘贴小红书或抖音主页 URL；如果已经知道账号 ID，也可以直接录入。"}
        </p>

        <label>
          平台
          <select
            value={form.platform}
            onChange={(event) => setForm((state) => ({ ...state, platform: event.target.value }))}
          >
            <option value="xhs">小红书</option>
            <option value="dy">抖音</option>
          </select>
        </label>

        <label>
          主页 URL
          <input
            type="text"
            value={form.profileUrl}
            onChange={(event) => setForm((state) => ({ ...state, profileUrl: event.target.value }))}
            placeholder="https://www.xiaohongshu.com/user/profile/..."
          />
        </label>

        <label>
          账号 ID
          <input
            type="text"
            value={form.creatorId}
            onChange={(event) => setForm((state) => ({ ...state, creatorId: event.target.value }))}
            placeholder="URL 为空时填写"
          />
        </label>

        <label>
          昵称
          <input
            type="text"
            value={form.displayName}
            onChange={(event) => setForm((state) => ({ ...state, displayName: event.target.value }))}
            placeholder={isCreatorMonitor ? "合作达人昵称，可选" : "可选；留空时自动获取真实昵称"}
          />
        </label>

        <label>
          备注
          <input
            type="text"
            value={form.notes}
            onChange={(event) => setForm((state) => ({ ...state, notes: event.target.value }))}
            placeholder={isCreatorMonitor ? "合作项目 / 宣发批次，可选" : "可选"}
          />
        </label>

        {message ? <div className="cmw-add-form__msg">{message}</div> : null}

        <div className="cmw-add-form__actions">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting ? <Loader2 size={14} className="spin" /> : <Plus size={14} />}
            保存
          </Button>
        </div>
      </form>
    </Drawer>
  );
}
