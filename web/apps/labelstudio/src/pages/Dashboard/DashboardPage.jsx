import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@humansignal/ui";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell,
} from "recharts";
import { Spinner } from "../../components";
import { useAPI } from "../../providers/ApiProvider";
import { useProject } from "../../providers/ProjectProvider";
import { cn } from "../../utils/bem";
import "./DashboardPage.prefix.css";

const rootClass = cn("dashboard");

const CHART_COLORS = [
  "#4F7CFF", "#FF6B6B", "#51CF66", "#FFD43B",
  "#CC5DE8", "#20C997", "#FF922B", "#845EF7",
  "#339AF0", "#F06595", "#94D82D", "#FCC419",
];

const formatLeadTime = (seconds) => {
  if (!seconds) return "N/A";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
};

export const DashboardPage = () => {
  const api = useAPI();
  const { project } = useProject();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  const fetchDashboard = useCallback(async () => {
    if (!project?.id) return;
    setLoading(true);
    const response = await api.callApi("projectDashboard", {
      params: { pk: project.id, days },
    });
    if (response) setData(response);
    setLoading(false);
  }, [project?.id, days]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  if (loading || !data) {
    return (
      <div className={rootClass.elem("loading").toClassName()}>
        <Spinner size={64} />
      </div>
    );
  }

  const { overview, label_distribution, annotator_stats, timeline } = data;

  const labelData = [];
  if (label_distribution) {
    Object.entries(label_distribution).forEach(([key, labels]) => {
      if (typeof labels === "object") {
        Object.entries(labels).forEach(([label, count]) => {
          labelData.push({ name: label, value: count });
        });
      }
    });
  }

  return (
    <div className={rootClass.toClassName()}>
      <div className={rootClass.elem("header").toClassName()}>
        <h1 className={rootClass.elem("title").toClassName()}>{project.title}</h1>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select
            className={rootClass.elem("period-select").toClassName()}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <Link to={`/projects/${project.id}/data`} style={{ textDecoration: "none" }}>
            <Button size="small">Label</Button>
          </Link>
        </div>
      </div>

      {/* Progress Bar */}
      <div className={rootClass.elem("progress-section").toClassName()}>
        <p className={rootClass.elem("progress-title").toClassName()}>Overall Project Progress</p>
        <div className={rootClass.elem("progress-bar-wrapper").toClassName()}>
          <div
            className={rootClass.elem("progress-bar-fill").toClassName()}
            style={{ width: `${overview.completion_percentage}%` }}
          />
        </div>
        <div className={rootClass.elem("progress-legend").toClassName()}>
          <span>
            <i className={rootClass.elem("progress-dot").mod({ annotated: true }).toClassName()} />
            {overview.labeled_tasks} Annotated {overview.completion_percentage}%
          </span>
          <span>
            <i className={rootClass.elem("progress-dot").mod({ remaining: true }).toClassName()} />
            {overview.unlabeled_tasks} Remaining {overview.total_tasks > 0 ? Math.round((overview.unlabeled_tasks / overview.total_tasks) * 100) : 0}%
          </span>
          <span>{overview.total_tasks} Total</span>
        </div>
      </div>

      {/* Stats Cards */}
      <div className={rootClass.elem("stats").toClassName()}>
        <div className={rootClass.elem("stat-card").toClassName()}>
          <p className={rootClass.elem("stat-label").toClassName()}>Annotated Tasks</p>
          <p className={rootClass.elem("stat-value").toClassName()}>{overview.labeled_tasks}</p>
          <p className={rootClass.elem("stat-sub").toClassName()}>
            {overview.total_annotations} Annotations
          </p>
        </div>
        <div className={rootClass.elem("stat-card").toClassName()}>
          <p className={rootClass.elem("stat-label").toClassName()}>Total Annotations</p>
          <p className={rootClass.elem("stat-value").toClassName()}>{overview.total_annotations}</p>
        </div>
        <div className={rootClass.elem("stat-card").toClassName()}>
          <p className={rootClass.elem("stat-label").toClassName()}>Completion</p>
          <p className={rootClass.elem("stat-value").toClassName()}>{overview.completion_percentage}%</p>
          <p className={rootClass.elem("stat-sub").toClassName()}>
            {overview.total_tasks} Total Tasks
          </p>
        </div>
        <div className={rootClass.elem("stat-card").toClassName()}>
          <p className={rootClass.elem("stat-label").toClassName()}>Remaining Tasks</p>
          <p className={rootClass.elem("stat-value").toClassName()}>{overview.unlabeled_tasks}</p>
        </div>
      </div>

      {/* Charts */}
      <div className={rootClass.elem("charts").toClassName()}>
        {/* Annotations Timeline */}
        <div className={rootClass.elem("chart-card").toClassName()}>
          <p className={rootClass.elem("chart-title").toClassName()}>Annotations Timeline</p>
          {timeline.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={timeline}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-neutral-border)" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => {
                    const d = new Date(v);
                    return `${d.getMonth() + 1}/${d.getDate()}`;
                  }}
                />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip
                  labelFormatter={(v) => new Date(v).toLocaleDateString()}
                  contentStyle={{
                    background: "var(--color-neutral-surface)",
                    border: "1px solid var(--color-neutral-border)",
                    borderRadius: 4,
                  }}
                />
                <Bar dataKey="count" name="Annotations" fill="#4F7CFF" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 280, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-neutral-content-subtler)" }}>
              No annotation data for this period
            </div>
          )}
        </div>

        {/* Label Distribution */}
        <div className={rootClass.elem("chart-card").toClassName()}>
          <p className={rootClass.elem("chart-title").toClassName()}>Label Distribution</p>
          {labelData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={labelData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {labelData.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 280, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-neutral-content-subtler)" }}>
              No label data available
            </div>
          )}
        </div>

        {/* Annotator Performance */}
        <div className={rootClass.elem("chart-card").toClassName()} style={{ gridColumn: "1 / -1" }}>
          <p className={rootClass.elem("chart-title").toClassName()}>Annotator Performance</p>
          {annotator_stats.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={annotator_stats} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-neutral-border)" />
                <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 11 }}
                  width={120}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-neutral-surface)",
                    border: "1px solid var(--color-neutral-border)",
                    borderRadius: 4,
                  }}
                  formatter={(value, name) => {
                    if (name === "avg_lead_time_seconds") return [formatLeadTime(value), "Avg Time"];
                    return [value, "Annotations"];
                  }}
                />
                <Legend />
                <Bar dataKey="annotation_count" name="Annotations" fill="#4F7CFF" radius={[0, 3, 3, 0]} />
                <Bar dataKey="avg_lead_time_seconds" name="Avg Time (s)" fill="#51CF66" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 280, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-neutral-content-subtler)" }}>
              No annotator data for this period
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

DashboardPage.title = "Dashboard";
DashboardPage.path = "/dashboard";
