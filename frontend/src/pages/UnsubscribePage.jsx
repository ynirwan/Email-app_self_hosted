/**
 * frontend/src/pages/UnsubscribePage.jsx
 *
 * Public page — no auth required.
 * Route: /unsubscribe/:token
 *
 * Flow:
 *   1. On mount, calls GET /api/t/verify/:token to validate and get masked email.
 *   2. Shows confirm button. On click, calls POST /api/t/u/:token.
 *   3. On success, shows confirmation. On error, shows appropriate message.
 *
 * This page works even when the user is not logged in, so it uses
 * raw fetch() rather than the authenticated API client.
 */

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

const BASE = import.meta.env.VITE_API_URL || "";

// ── icons (inline SVG — no deps needed for a public page) ─────────────────────
const IconCheck = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ width: 32, height: 32 }}
  >
    <polyline points="20 6 9 17 4 12" />
  </svg>
);
const IconX = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ width: 32, height: 32 }}
  >
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);
const IconMail = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ width: 20, height: 20 }}
  >
    <rect x="2" y="4" width="20" height="16" rx="2" />
    <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
  </svg>
);

export default function UnsubscribePage() {
  const { token } = useParams();

  const [phase, setPhase] = useState("verifying"); // verifying | confirm | loading | done | already_done | error
  const [emailMasked, setEmailMasked] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  // ── 1. Verify token on mount ───────────────────────────────────────────────
  useEffect(() => {
    if (!token) {
      setPhase("error");
      setErrorMsg("No token provided.");
      return;
    }

    fetch(`${BASE}/api/t/verify/${token}`)
      .then(async (r) => {
        if (r.status === 410) {
          setPhase("already_done");
          return;
        }
        if (!r.ok) {
          const data = await r.json().catch(() => ({}));
          throw new Error(data.detail || "Invalid link");
        }
        const data = await r.json();
        setEmailMasked(data.email_masked || "");
        setPhase("confirm");
      })
      .catch((e) => {
        setPhase("error");
        setErrorMsg(
          e.message || "This unsubscribe link is invalid or has expired.",
        );
      });
  }, [token]);

  // ── 2. Confirm unsubscribe ─────────────────────────────────────────────────
  const handleConfirm = async () => {
    setPhase("loading");
    try {
      const r = await fetch(`${BASE}/api/t/u/${token}`, { method: "POST" });
      if (r.status === 400) {
        const data = await r.json().catch(() => ({}));
        if (data.detail?.includes("already")) {
          setPhase("already_done");
          return;
        }
        throw new Error(data.detail || "Unsubscribe failed");
      }
      if (!r.ok) throw new Error("Unsubscribe failed. Please try again.");
      setPhase("done");
    } catch (e) {
      setPhase("error");
      setErrorMsg(e.message);
    }
  };

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        {/* Logo / brand */}
        <div style={styles.brand}>
          <div style={styles.brandDot} />
          <span style={styles.brandName}>ZeniPost</span>
        </div>

        {phase === "verifying" && <VerifyingState />}
        {phase === "confirm" && (
          <ConfirmState email={emailMasked} onConfirm={handleConfirm} />
        )}
        {phase === "loading" && <LoadingState />}
        {phase === "done" && <DoneState />}
        {phase === "already_done" && <AlreadyDoneState />}
        {phase === "error" && <ErrorState message={errorMsg} />}
      </div>
    </div>
  );
}

// ── sub-states ─────────────────────────────────────────────────────────────────

function VerifyingState() {
  return (
    <div style={styles.center}>
      <div style={styles.spinner} />
      <p style={styles.subtitle}>Verifying your link…</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div style={styles.center}>
      <div style={styles.spinner} />
      <p style={styles.subtitle}>Processing…</p>
    </div>
  );
}

function ConfirmState({ email, onConfirm }) {
  return (
    <div style={styles.center}>
      <div style={{ ...styles.iconBubble, background: "#fef3c7" }}>
        <IconMail />
      </div>
      <h1 style={styles.heading}>Unsubscribe from emails?</h1>
      {email && (
        <p style={styles.subtitle}>
          We'll stop sending emails to <strong>{email}</strong>.
        </p>
      )}
      <p
        style={{
          ...styles.subtitle,
          marginTop: 4,
          fontSize: 13,
          color: "#9ca3af",
        }}
      >
        This applies to all future campaigns from this sender.
      </p>
      <button style={styles.btn} onClick={onConfirm}>
        Yes, unsubscribe me
      </button>
      <p style={styles.hint}>Changed your mind? Just close this tab.</p>
    </div>
  );
}

function DoneState() {
  return (
    <div style={styles.center}>
      <div style={{ ...styles.iconBubble, background: "#dcfce7" }}>
        <span style={{ color: "#16a34a" }}>
          <IconCheck />
        </span>
      </div>
      <h1 style={styles.heading}>Successfully Unsubscribed</h1>
      <p style={styles.subtitle}>
        You've been removed from this mailing list and won't receive these
        emails anymore.
      </p>
      <p style={{ ...styles.hint, marginTop: 20 }}>
        Changed your mind? Contact the sender to re-subscribe.
      </p>
    </div>
  );
}

function AlreadyDoneState() {
  return (
    <div style={styles.center}>
      <div style={{ ...styles.iconBubble, background: "#dcfce7" }}>
        <span style={{ color: "#16a34a" }}>
          <IconCheck />
        </span>
      </div>
      <h1 style={styles.heading}>Already Unsubscribed</h1>
      <p style={styles.subtitle}>
        You're already removed from this mailing list. No further action needed.
      </p>
    </div>
  );
}

function ErrorState({ message }) {
  return (
    <div style={styles.center}>
      <div style={{ ...styles.iconBubble, background: "#fee2e2" }}>
        <span style={{ color: "#dc2626" }}>
          <IconX />
        </span>
      </div>
      <h1 style={{ ...styles.heading, color: "#dc2626" }}>Invalid Link</h1>
      <p style={styles.subtitle}>
        {message || "This unsubscribe link is invalid or has expired."}
      </p>
      <p style={styles.hint}>
        If you keep receiving unwanted emails, reply to any of them and ask to
        be removed.
      </p>
    </div>
  );
}

// ── styles (plain JS objects — no Tailwind needed on a public page) ────────────
const styles = {
  page: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "24px 16px",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  card: {
    background: "#ffffff",
    borderRadius: 20,
    boxShadow: "0 8px 40px rgba(0,0,0,0.10)",
    padding: "40px 36px 48px",
    maxWidth: 440,
    width: "100%",
    textAlign: "center",
  },
  brand: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    marginBottom: 32,
  },
  brandDot: {
    width: 28,
    height: 28,
    borderRadius: 8,
    background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
  },
  brandName: {
    fontWeight: 700,
    fontSize: 18,
    color: "#111827",
    letterSpacing: "-0.3px",
  },
  center: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 12,
  },
  iconBubble: {
    width: 72,
    height: 72,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 8,
  },
  heading: {
    fontSize: 22,
    fontWeight: 700,
    color: "#111827",
    margin: "0 0 4px",
    lineHeight: 1.3,
  },
  subtitle: {
    fontSize: 15,
    color: "#6b7280",
    lineHeight: 1.6,
    margin: 0,
    maxWidth: 340,
  },
  btn: {
    marginTop: 20,
    padding: "13px 32px",
    background: "#ef4444",
    color: "#fff",
    border: "none",
    borderRadius: 10,
    fontWeight: 600,
    fontSize: 15,
    cursor: "pointer",
    transition: "background 0.15s",
    width: "100%",
    maxWidth: 280,
  },
  hint: {
    fontSize: 12,
    color: "#9ca3af",
    margin: "8px 0 0",
  },
  spinner: {
    width: 36,
    height: 36,
    border: "3px solid #e5e7eb",
    borderTop: "3px solid #6366f1",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
    marginBottom: 8,
  },
};

// Inject keyframe animation globally (only once)
if (typeof document !== "undefined" && !document.getElementById("unsub-spin")) {
  const style = document.createElement("style");
  style.id = "unsub-spin";
  style.textContent = "@keyframes spin { to { transform: rotate(360deg); } }";
  document.head.appendChild(style);
}
