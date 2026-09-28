"use client";

import { useEffect, useState } from "react";
import { ApiError, workspaceApi, type CurrentIdentity } from "@/lib/api";

export function SettingsPanel() {
  const [identity, setIdentity] = useState<CurrentIdentity | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    workspaceApi
      .me()
      .then((value) => active && setIdentity(value))
      .catch((cause) => active && setError(cause instanceof ApiError ? cause.message : "Could not load workspace settings."))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="management-page">
      <header className="management-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-rule" />WORKSPACE</div>
          <h1>Settings</h1>
          <p>Workspace preferences and account controls.</p>
        </div>
      </header>
      {loading ? (
        <div className="loading-surface">Loading settings...</div>
      ) : error ? (
        <div className="feedback feedback-error" role="alert">{error}</div>
      ) : identity ? (
        <div className="settings-grid">
          <div className="settings-card">
            <span className="section-kicker">ACCOUNT</span>
            <h2>{identity.user.display_name}</h2>
            <p className="settings-row"><span>Email</span><strong>{identity.user.email}</strong></p>
            <p className="settings-row"><span>Status</span><strong>{identity.user.is_active ? "Active" : "Inactive"}</strong></p>
          </div>
          <div className="settings-card">
            <span className="section-kicker">WORKSPACE</span>
            <h2>{identity.workspace.name}</h2>
            <p className="settings-row"><span>Slug</span><strong>{identity.workspace.slug}</strong></p>
            <p className="settings-row"><span>Your role</span><strong className="role-tag">{identity.role}</strong></p>
          </div>
        </div>
      ) : null}
      <p className="settings-footnote">More workspace preferences and member management arrive in a later Vantage phase.</p>
    </section>
  );
}
